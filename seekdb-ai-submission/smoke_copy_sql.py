#!/usr/bin/env python3
"""On-server SQL checks for native C++ CSV/JSON/NDJSON/glob adapter.
Starts patched seekdb on isolated 2885 and never touches StepFun 2881 / AI 2884.
"""
from pathlib import Path
import json, os, socket, subprocess, sys, tempfile, time

ROOT=Path("/workspaces/seekdb-core")
BINARY=Path("/tmp/seekdb-build/bin/src/observer/seekdb")
CLIENT=ROOT/"deps/3rd/u01/obclient/bin/obclient"
DEPLOY=ROOT/"tools/deploy/sdb.py"
BUILD_EXIT=Path("/tmp/seekdb-file-sql-build.exit")
PORT=2887
DATA=Path("/tmp/seekdb-file-sql-copy-"+str(os.getpid()))
REPORT=Path("/tmp/seekdb-file-sql-copy-report.json")
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
        print("ERROR: isolated 2885 port already in use. Refusing to connect to unknown DB.")
        return 2
    DATA.mkdir(parents=True,exist_ok=True)
    (DATA/"rows.csv").write_text(
        'id,name,amount\n1,Alice,1.25\n2,"Bob, Inc.",2.50\n3,Charlie,3.00\n',
        encoding="utf-8")
    (DATA/"events.json").write_text(
        '[{"id":1,"team":"A"},{"id":2,"team":"B"}]',encoding="utf-8")
    (DATA/"events.ndjson").write_text(
        '{"id":1,"team":"A"}\n{"id":2,"team":"B"}\n',encoding="utf-8")
    instance=Path(tempfile.mkdtemp(prefix="seekdb-file-sql-2887-",dir="/tmp"))
    env=os.environ.copy()
    env["SEEKDB_FILE_SQL_ROOT"]=str(DATA)
    lib=ROOT/"deps/3rd/u01/obclient/lib"
    env["LD_LIBRARY_PATH"]=str(lib)+(":"+env["LD_LIBRARY_PATH"]
                                   if env.get("LD_LIBRARY_PATH") else "")
    start=run([sys.executable,str(DEPLOY),"start","--binary",str(BINARY),
               "--base-dir",str(instance),"--port",str(PORT)],env,timeout=50)
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
        p=run(cli+(["-D"+DB] if use_db else [])+["-e",statement],env)
        return p.returncode,p.stdout.strip(),p.stderr.strip()
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
       lambda rc,out:rc==0 and out=="1"),
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
       lambda rc,out:rc!=0)
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
    print("FILE_SQL_SMOKE_PASS" if all_ok else "FILE_SQL_SMOKE_FAIL")
    print("REPORT:",REPORT)
    print("Isolated database remains running on 2885 for debugging.")
    return 0 if all_ok else 1

if __name__=="__main__":
    sys.exit(main())
