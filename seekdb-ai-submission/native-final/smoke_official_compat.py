#!/usr/bin/env python3
"""On-server SQL checks for native C++ CSV/JSON/NDJSON/glob adapter.
Starts patched seekdb on isolated 2885 and never touches StepFun 2881 / AI 2884.
"""
from pathlib import Path
import json, os, socket, subprocess, sys, tempfile, time, csv

ROOT=Path("/workspaces/seekdb-core")
BINARY=Path("/tmp/seekdb-build/bin/src/observer/seekdb")
CLIENT=ROOT/"deps/3rd/u01/obclient/bin/obclient"
DEPLOY=ROOT/"tools/deploy/sdb.py"
BUILD_EXIT=Path("/tmp/seekdb-official-compat-build.exit")
PORT=2891
DATA=Path("/tmp/seekdb-official-compat-"+str(os.getpid()))
REPORT=Path("/tmp/seekdb-official-compat-report.json")
DB="seekdb_native_file_sql_smoke"

def run(argv,env=None,cwd=ROOT,timeout=160):
    return subprocess.run(argv,cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout)

def main():
    if not BUILD_EXIT.exists() or BUILD_EXIT.read_text().strip()!="0":
        print("ERROR: new native build has not completed with exit code 0.")
        return 2
    for f in (BINARY,CLIENT,DEPLOY):
        if not f.is_file():
            print("ERROR: missing:",f)
            return 2
    sock=socket.socket()
    sock.settimeout(.5)
    occupied=sock.connect_ex(("127.0.0.1",PORT))==0
    sock.close()
    if occupied:
        print("ERROR: isolated 2891 port already in use. Refusing to connect to unknown DB.")
        return 2
    DATA.mkdir(parents=True,exist_ok=True)
    (DATA/"rows.csv").write_text(
        'id,name,amount\n1,Alice,1.25\n2,"Bob, Inc.",2.50\n3,Charlie,3.00\n',
        encoding="utf-8")
    (DATA/"events.json").write_text(
        '[{"id":1,"team":"A"},{"id":2,"team":"B"}]',encoding="utf-8")
    (DATA/"events.ndjson").write_text(
        '{"id":1,"team":"A"}\n{"id":2,"team":"B"}\n',encoding="utf-8")
    (DATA/"official_basic.csv").write_text(
        'id,name,score,active,day,created,note,id\n'
        '1,Alice,98.5,true,2026-08-01,2026-08-01 10:11:12,"hello,\nworld",101\n'
        '2,Bob,87,false,,,plain,102\n'
        '3,Chen,90.25,true,2026-08-03,2026-08-03T12:13:14,"say ""hi""",103\n',
        encoding="utf-8")
    (DATA/"official_basic.jsonl").write_text(
        '{"id":1,"name":"Alice","score":98.5,"active":true}\n'
        '{"id":2,"name":"Bob","active":false,"day":"2026-08-02"}\n'
        '{"id":3,"name":"Chen","score":90,"active":true,"note":"ok"}\n',
        encoding="utf-8")
    (DATA/"bad_nested.jsonl").write_text(
        '{"id":1,"values":[1,2]}\n',encoding="utf-8")
    # Parquet tests use the actual competition fixture and three additional
    # generated format-compliance fixtures. No database content is hardcoded.
    import shutil
    fixtures=Path(__file__).resolve().parent/"fixtures"
    for name in ("simple.parquet","multi_nullable.parquet",
                 "page_v2.parquet","dictionary.parquet"):
        shutil.copyfile(fixtures/name,DATA/name)
    instance=Path(tempfile.mkdtemp(prefix="seekdb-official-compat-2891-",dir="/tmp"))
    env=os.environ.copy()
    env["SEEKDB_FILE_SQL_ROOT"]=str(DATA)
    lib=ROOT/"deps/3rd/u01/obclient/lib"
    env["LD_LIBRARY_PATH"]=str(lib)+(":"+env["LD_LIBRARY_PATH"]
                                   if env.get("LD_LIBRARY_PATH") else "")
    start=run([sys.executable,str(DEPLOY),"start","--binary",str(BINARY),
               "--base-dir",str(instance),"--port",str(PORT),"--parameter","log_disk_size=2G"],env,timeout=50)
    print("START:",start.stdout.strip(),start.stderr.strip()[:450])
    if start.returncode:
        return 2
    ready=run([sys.executable,str(DEPLOY),"wait-ready","--client",str(CLIENT),
               "--base-dir",str(instance),"--port",str(PORT),"--timeout","180"],env,timeout=210)
    print("WAIT_READY:",ready.stdout.strip(),ready.stderr.strip()[:450])
    if ready.returncode:
        log=instance/"log/seekdb.log"
        if log.exists():
            print("LOG:", "\n".join(log.read_text(errors="replace").splitlines()[-15:])[:2400])
        return 2
    cli=[str(CLIENT),"-h127.0.0.1","-P"+str(PORT),"-uroot","-A","-N","-B"]
    def sql(statement,use_db=True):
        p=run(cli+(["-D"+DB] if use_db else [])+["-e","SET SESSION enable_file_sql = ON; "+statement],env)
        return p.returncode,(p.stdout.strip() or p.stderr.strip()),p.stderr.strip()
    rc,stdout,stderr=sql("CREATE DATABASE IF NOT EXISTS "+DB,False)
    if rc:
        print("ERROR: creating test database failed:",stderr)
        return 2
    checks=[
      ("file CSV rows", "SELECT id,name FROM read_csv('rows.csv') ORDER BY id;",
       lambda rc,out:rc==0 and len(out.splitlines())==3 and "Bob, Inc." in out),
      ("file CSV numeric aggregate", "SELECT SUM(amount) FROM read_csv('rows.csv');",
       lambda rc,out:rc==0 and abs(float(out)-6.75)<1e-6),
      ("JSON rows", "SELECT COUNT(*) FROM read_json('events.json');",
       lambda rc,out:rc==0 and out=="2"),
      ("NDJSON rows", "SELECT COUNT(*) FROM read_ndjson('events.ndjson');",
       lambda rc,out:rc==0 and out=="2"),
      ("SQL native file JOIN",
       "SELECT c.name,j.team FROM read_csv('rows.csv') c "
       "JOIN read_ndjson('events.ndjson') j ON c.id=j.id ORDER BY c.id;",
       lambda rc,out:rc==0 and len(out.splitlines())==2 and "Alice" in out and "Bob, Inc." in out),
      ("glob lists local CSV", "SELECT COUNT(*) FROM glob('*.csv');",
       lambda rc,out:rc==0 and out=="2"),
      ("file path traversal rejected", "SELECT * FROM read_csv('/etc/passwd');",
       lambda rc,out:rc!=0),
      ("normal SQL unaffected", "SELECT 1;",
       lambda rc,out:rc==0 and out=="1"),
      ("COPY create destination table",
       "CREATE TABLE copy_target (id INT PRIMARY KEY, name VARCHAR(120), amount DOUBLE);",
       lambda rc,out:rc==0),
      ("COPY CSV FROM source",
       "COPY copy_target FROM 'rows.csv' WITH (FORMAT CSV);",
       lambda rc,out:rc==0),
      ("COPY FROM persisted rows",
       "SELECT COUNT(*),SUM(amount) FROM copy_target;",
       lambda rc,out:rc==0 and out.split()==["3","6.75"]),
      ("COPY query TO CSV",
       "COPY (SELECT id,name,amount FROM copy_target ORDER BY id) "
       "TO 'copy_result.csv' WITH (FORMAT CSV, HEADER FALSE);",
       lambda rc,out:rc==0 and (DATA/"copy_result.csv").is_file()
         and len((DATA/"copy_result.csv").read_text().splitlines())==3),
      ("COPY headerless output can be read (first line treated as CSV header)",
       "SELECT COUNT(*) FROM read_csv('copy_result.csv');",
       lambda rc,out:rc==0 and out=="2"),
      ("COPY refuses overwrite",
       "COPY (SELECT id FROM copy_target) TO 'copy_result.csv';",
       lambda rc,out:rc!=0),
      ("COPY protects outside path",
       "COPY (SELECT 1) TO '/tmp/outside-seekdb-copy.csv';",
       lambda rc,out:rc!=0),
      ("Parquet official fixture COUNT MIN MAX SUM",
       "SELECT COUNT(*),MIN(c1),MAX(c1),SUM(c1) FROM read_parquet('simple.parquet');",
       lambda rc,out:rc==0 and out.split()==["7","0","6","21"]),
      ("Parquet official fixture WHERE",
       "SELECT COUNT(*) FROM read_parquet('simple.parquet') p WHERE p.c1 >= 3;",
       lambda rc,out:rc==0 and out=="4"),
      ("Parquet multi-rowgroup nullable COUNT SUM",
       "SELECT COUNT(*),COUNT(id),SUM(id) FROM read_parquet('multi_nullable.parquet');",
       lambda rc,out:rc==0 and out.split()==["6","4","56"]),
      ("Parquet multi-rowgroup strings",
       "SELECT COUNT(*) FROM read_parquet('multi_nullable.parquet') WHERE label IS NOT NULL;",
       lambda rc,out:rc==0 and out=="6"),
      ("Parquet page v2 nullable",
       "SELECT COUNT(*),COUNT(id) FROM read_parquet('page_v2.parquet');",
       lambda rc,out:rc==0 and out.split()==["6","4"]),
      ("Parquet dictionary encoding",
       "SELECT COUNT(*) FROM read_parquet('dictionary.parquet') WHERE color='blue';",
       lambda rc,out:rc==0 and out=="2"),
      ("Parquet+CSV native SQL JOIN",
       "SELECT COUNT(*) FROM read_parquet('simple.parquet') p "
       "JOIN read_csv('rows.csv') c ON p.c1=c.id;",
       lambda rc,out:rc==0 and out=="3"),
      ("Parquet rejects missing files",
       "SELECT * FROM read_parquet('missing.parquet');",
       lambda rc,out:rc!=0),
      ("Official CSV inferred id sum, double avg and boolean sum",
       "SELECT COUNT(*),SUM(id),ROUND(AVG(score),2),SUM(active) "
       "FROM read_csv('official_basic.csv',header=true,sample_size=-1);",
       lambda rc,out:rc==0 and out.split()==["3","6","91.92","2"]),
      ("Official CSV duplicate header id__2",
       "SELECT id,id__2 FROM read_csv('official_basic.csv') ORDER BY id;",
       lambda rc,out:rc==0 and len(out.splitlines())==3
          and out.splitlines()[0].split()==["1","101"]),
      ("Official CSV DATE type",
       "SELECT MIN(day),MAX(day) FROM read_csv('official_basic.csv');",
       lambda rc,out:rc==0 and out.split()==["2026-08-01","2026-08-03"]),
      ("Official CSV DATETIME type with T delimiter",
       "SELECT COUNT(created) FROM read_csv('official_basic.csv');",
       lambda rc,out:rc==0 and out=="2"),
      ("Official CSV multiline and escaped quote",
       "SELECT COUNT(*) FROM read_csv('official_basic.csv') "
       "WHERE note LIKE '%world%' OR note LIKE '%hi%';",
       lambda rc,out:rc==0 and out=="2"),
      ("Official JSONL union schema with named format",
       "SELECT COUNT(*),COUNT(score),COUNT(day),SUM(active) "
       "FROM read_json('official_basic.jsonl',format='newline_delimited');",
       lambda rc,out:rc==0 and out.split()==["3","2","1","2"]),
      ("Official JSONL alias and WHERE",
       "SELECT COUNT(*) FROM read_json('official_basic.jsonl',"
       "format='newline_delimited') j WHERE j.id>=2;",
       lambda rc,out:rc==0 and out=="2"),
      ("Read CSV without header names",
       "SELECT COUNT(*) FROM read_csv('official_basic.csv',header=false);",
       lambda rc,out:rc==0 and out=="4"),
      ("Sample size other than -1 is denied",
       "SELECT * FROM read_csv('official_basic.csv',sample_size=10);",
       lambda rc,out:rc!=0),
      ("JSONL nested values explicitly denied",
       "SELECT * FROM read_json('bad_nested.jsonl',format='newline_delimited');",
       lambda rc,out:rc!=0),
      ("Official DESCRIBE file SQL metadata",
       "DESCRIBE SELECT * FROM read_csv('official_basic.csv');",
       lambda rc,out:rc==0 and len(out.splitlines())==8
           and any("id__2" in line and "BIGINT" in line for line in out.splitlines())
           and any("created" in line and "DATETIME" in line for line in out.splitlines())),
      ("Official COPY HEADER NULLSTR export",
       "COPY (SELECT id,name,score FROM read_csv('official_basic.csv') ORDER BY id) "
       "TO 'official_export.csv' (FORMAT CSV, HEADER, NULLSTR 'NULL');",
       lambda rc,out:rc==0 and (DATA/"official_export.csv").is_file()),
      ("Official COPY has correct header and 3 data rows",
       "SELECT COUNT(*) FROM read_csv('official_export.csv');",
       lambda rc,out:rc==0 and out=="3"),
      ("Official COPY preserves numeric aggregate on round trip",
       "SELECT SUM(id),ROUND(AVG(score),2) FROM read_csv('official_export.csv');",
       lambda rc,out:rc==0 and out.split()==["6","91.92"]),
      ("COPY HEADER FALSE remains backward compatible",
       "COPY (SELECT id,name,score FROM read_csv('official_basic.csv')) "
       "TO 'official_no_header.csv' WITH (FORMAT CSV, HEADER FALSE);",
       lambda rc,out:rc==0 and (DATA/"official_no_header.csv").is_file()),
      ("COPY HEADER refuses existing target",
       "COPY (SELECT id,name,score FROM read_csv('official_basic.csv')) "
       "TO 'official_export.csv' (FORMAT CSV, HEADER);",
       lambda rc,out:rc!=0),
      ("COPY NULLSTR arbitrary nested expression",
       "COPY (SELECT id,CASE WHEN id=2 THEN NULL ELSE name END AS name "
       "FROM read_csv('official_basic.csv')) "
       "TO 'official_null.csv' (FORMAT CSV, HEADER, NULLSTR 'NULL');",
       lambda rc,out:rc==0 and (DATA/"official_null.csv").is_file()
          and list(csv.reader((DATA/"official_null.csv").open(newline="")))[2][1]=="NULL"),
      ("Public test expects positional format syntax error 1064",
       "SELECT * FROM read_csv('official_basic.csv','xml');",
       lambda rc,out:rc!=0 and "1064" in out),
      ("Public test expects unsupported sample size error 1235",
       "SELECT * FROM read_csv('official_basic.csv',sample_size=10);",
       lambda rc,out:rc!=0 and "1235" in out)
    ]
    report={"instance":str(instance),"port":PORT,"checks":[]}
    all_ok=True
    for name,statement,checker in checks:
        try:
            rc,out,err=sql(statement)
            passed=checker(rc,out)
            print(("PASS" if passed else "FAIL"),name,"->",(out or err)[:220].replace("\n"," | "))
            report["checks"].append({"name":name,"pass":passed,"exit":rc,
                                     "output":out[:800],"stderr":err[:800]})
            all_ok=all_ok and passed
        except Exception as exc:
            print("FAIL",name,exc)
            report["checks"].append({"name":name,"pass":False,"exception":str(exc)})
            all_ok=False
    report["success"]=all_ok
    REPORT.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("FILE_OFFICIAL_COMPAT_SQL_PASS" if all_ok else "FILE_OFFICIAL_COMPAT_SQL_FAIL")
    print("REPORT:",REPORT)
    print("Isolated database remains running on port 2891 for debugging.")
    return 0 if all_ok else 1

if __name__=="__main__":
    sys.exit(main())
