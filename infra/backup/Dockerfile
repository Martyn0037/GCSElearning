# infra/backup/Dockerfile
# Nightly pg_dump with local retention, optional upload to S3, and a weekly
# restore test. Same Postgres major version as the database.
FROM postgres:16-alpine

RUN apk upgrade --no-cache && apk add --no-cache aws-cli tzdata \
    && addgroup -S backup && adduser -S -G backup -h /home/backup backup \
    && mkdir -p /backups && chown backup:backup /backups

COPY --chmod=0755 backup.sh restore-test.sh entrypoint.sh /usr/local/bin/

USER backup
ENV TZ=Europe/London
HEALTHCHECK --interval=5m --timeout=10s --start-period=30s \
  CMD find /backups/.last-success -mmin -1560 | grep -q . || exit 1
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
