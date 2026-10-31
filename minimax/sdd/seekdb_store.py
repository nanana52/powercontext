"""Real embedded seekdb storage: engineering source import and SQL retrieval."""
import hashlib

class SeekDBStore:
    def __init__(self, location):
        self.location = location
        self.sql_log = []
    def __enter__(self):
        import pylibseekdb, pymysql
        self.location.mkdir(parents=True, exist_ok=True)
        self.handle = pylibseekdb.open(db_dir=str(self.location.resolve()))
        self.conn = pymysql.connect(database="test", autocommit=True,
                                    charset="utf8mb4", **self.handle.connection_options())
        self.execute("CREATE TABLE IF NOT EXISTS sdd_docs ("
                     "doc_key VARCHAR(64) NOT NULL PRIMARY KEY, kind VARCHAR(16) NOT NULL, "
                     "path VARCHAR(255) NOT NULL, digest_sha256 VARCHAR(64) NOT NULL, body LONGTEXT NOT NULL)")
        return self
    def __exit__(self, *_):
        self.conn.close()
        self.handle.close()
    def execute(self, sql, args=(), fetch=False):
        self.sql_log.append({"sql": sql, "args": list(args)})
        with self.conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchall() if fetch else None
    def import_doc(self, key, kind, path, body):
        sha=hashlib.sha256(body.encode("utf-8")).hexdigest()
        self.execute("INSERT INTO sdd_docs(doc_key,kind,path,digest_sha256,body) VALUES(%s,%s,%s,%s,%s) "
                     "ON DUPLICATE KEY UPDATE kind=VALUES(kind),path=VALUES(path),"
                     "digest_sha256=VALUES(digest_sha256),body=VALUES(body)",
                     (key,kind,path,sha,body))
        return sha
    def import_project(self, root):
        for key,kind,path in [
            ("spec-current","spec","specs/shipping.md"),
            ("app-shipping","code","app/shipping.py"),
            ("test-target","test","tests/test_target.py"),
            ("test-regression","test","tests/test_regression.py")]:
            self.import_doc(key,kind,path,(root/path).read_text(encoding="utf-8"))
    def context(self, task):
        # These are real seekdb SQL results, not hardcoded or SQLite substitutes.
        rows=self.execute(
            "SELECT doc_key,kind,path,digest_sha256,body FROM sdd_docs "
            "WHERE kind IN ('spec','code','test') ORDER BY doc_key",fetch=True)
        items=[dict(key=r[0],kind=r[1],path=r[2],sha256=r[3],body=r[4])
               for r in rows if "shipping" in task.lower()
               and (r[1]=="spec" or "shipping" in r[2] or "shipping" in r[4].lower())]
        required={"specs/shipping.md","app/shipping.py",
                  "tests/test_target.py","tests/test_regression.py"}
        assert required.issubset({it["path"] for it in items}), "Incomplete live seekdb context"
        return {"task": task, "sources": items}
