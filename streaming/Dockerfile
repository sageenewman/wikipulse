# The image the streaming jobs run in: the official Spark image plus the connectors the
# jobs need, resolved at build time so a job starts without downloading anything.
# Decisions: docs/adr/0011-spark-bronze-job.md
# Built from the repository root; .dockerignore lets in only streaming/ and tests/spark/.
FROM apache/spark:4.1.3-python3@sha256:bf9d035a7c32a8ca46aa58d6348182ffd7d2dff6409206ecfbb3915ff1fef211 AS runtime

USER root

# Kafka source for Structured Streaming, Iceberg for Spark 4.1, and Iceberg's AWS module
# (S3FileIO and the AWS SDK it uses). Iceberg 1.12.0 is the newest release with a
# runtime for Spark 4.1; none exists yet for Spark 4.2.
ARG SPARK_PACKAGES=org.apache.spark:spark-sql-kafka-0-10_2.13:4.1.3,org.apache.iceberg:iceberg-spark-runtime-4.1_2.13:1.12.0,org.apache.iceberg:iceberg-aws-bundle:1.12.0

# spark-submit --packages resolves the connectors and their dependencies with Ivy. They
# are then copied onto Spark's own classpath, and the Ivy cache is removed.
RUN echo 'print("connectors resolved")' > /tmp/resolve.py \
    && /opt/spark/bin/spark-submit --conf spark.jars.ivy=/tmp/ivy --packages "$SPARK_PACKAGES" /tmp/resolve.py \
    && cp /tmp/ivy/jars/*.jar /opt/spark/jars/ \
    && rm -rf /tmp/ivy /tmp/resolve.py

# The same version as in uv.lock.
RUN python3 -m pip install --no-cache-dir "pydantic-settings==2.15.0"

# Checkpoints live on a volume mounted here; it must belong to the user the job runs as.
RUN mkdir -p /checkpoints && chown spark:spark /checkpoints

COPY --chown=spark:spark streaming/ /opt/wikipulse/streaming/
ENV PYTHONPATH=/opt/wikipulse

USER spark
WORKDIR /opt/wikipulse

# Spark in local mode: driver and executor in one JVM, one thread per core.
ENTRYPOINT ["/opt/spark/bin/spark-submit", "--master", "local[*]", "--driver-memory", "1g"]
CMD ["streaming/bronze.py"]


# The tests that need Spark, run on the same image and the same Python as the jobs:
# `make test-spark`. Not used by any service.
FROM runtime AS test

USER root
# The same version as in uv.lock.
RUN python3 -m pip install --no-cache-dir "pytest==9.1.1"
# Plain python3 (not spark-submit) does not see Spark's Python package; a .pth file adds
# it and its py4j bridge to the interpreter's path.
RUN site=$(python3 -c "import site; print(site.getsitepackages()[0])") \
    && mkdir -p "$site" \
    && { echo /opt/spark/python; ls /opt/spark/python/lib/py4j-*.zip; } > "$site/spark.pth"
COPY --chown=spark:spark tests/spark/ /opt/wikipulse/tests/spark/

USER spark
ENTRYPOINT ["python3", "-m", "pytest", "-p", "no:cacheprovider"]
CMD ["-q", "tests/spark"]
