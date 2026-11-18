"""Isolated stores keyed by (run_id, article_key), commit before acknowledgement."""
import time

import duckdb
import polars as pl

from common import FIELDS, SQL_COLUMNS, QUERIES


class SqlSink:
    def __init__(self, architecture, work):
        self.architecture = "A2" if architecture == "B0" else architecture
        if self.architecture == "A2":
            self.connection = duckdb.connect(str(work / "output.duckdb"))
            self.connection.execute("SET threads=1")
        else:
            import psycopg
            self.connection = psycopg.connect("host=postgres dbname=benchmark user=benchmark password=benchmark_local_only")
        # Database belongs exclusively to this compose project, serial runs only.
        self.connection.execute("DROP TABLE IF EXISTS output")
        self.connection.execute(f"CREATE TABLE output ({SQL_COLUMNS}, PRIMARY KEY(run_id, article_key))")
        if architecture == "A4":
            self.connection.commit()

    def write(self, rows, batch_id):
        marks = ",".join(["?" if self.architecture == "A2" else "%s"] * len(FIELDS))
        sql = f"INSERT INTO output ({','.join(FIELDS)}) VALUES ({marks}) ON CONFLICT(run_id,article_key) DO NOTHING"
        try:
            if self.architecture == "A2":
                batch = pl.DataFrame(rows, infer_schema_length=None).select(FIELDS)
                self.connection.register("input_batch", batch.to_arrow())
                self.connection.execute("BEGIN")
                self.connection.execute(f"INSERT INTO output ({','.join(FIELDS)}) SELECT * FROM input_batch ON CONFLICT(run_id,article_key) DO NOTHING")
                self.connection.execute("COMMIT")
                self.connection.unregister("input_batch")
            else:
                with self.connection.cursor() as cursor:
                    cursor.executemany(sql, [[r[k] for k in FIELDS] for r in rows])
                self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        return time.time()

    def rows(self):
        cursor = self.connection.execute(f"SELECT {','.join(FIELDS)} FROM output")
        return [dict(zip(FIELDS, row)) for row in cursor.fetchall()]

    def query(self, sql):
        return self.connection.execute(sql).fetchall()

    def close(self):
        self.connection.close()


class DeltaSink:
    def __init__(self, spark, work, run_id):
        from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType
        self.spark, self.path, self.run_id = spark, str(work / "delta"), run_id
        self.work = work
        self.schema = StructType([StructField(k, DoubleType() if k in ("sent_at", "processed_at")
                                              else LongType() if k in ("fatalities", "injuries")
                                              else StringType(), True) for k in FIELDS])
        self.started = False
        self.connection = None

    def write(self, rows, batch_id):
        data = self.spark.createDataFrame(rows, schema=self.schema)
        # Stable appId + batchId makes re-execution of a microbatch a no-op.
        (data.write.format("delta").mode("append")
         .option("txnAppId", self.run_id).option("txnVersion", batch_id).save(self.path))
        self.started = True
        return time.time()

    def export(self):
        start = time.perf_counter()
        path = str(self.work / "snapshot")
        self.spark.read.format("delta").load(self.path).write.mode("overwrite").parquet(path)
        self.connection = duckdb.connect()
        self.connection.execute("SET threads=1")
        self.connection.from_parquet(path + "/*.parquet").create_view("output")
        return time.perf_counter() - start

    def rows(self):
        return [dict(zip(FIELDS, row)) for row in self.connection.execute(f"SELECT {','.join(FIELDS)} FROM output").fetchall()]

    def query(self, sql):
        return self.connection.execute(sql).fetchall()

    def close(self):
        if self.connection:
            self.connection.close()
