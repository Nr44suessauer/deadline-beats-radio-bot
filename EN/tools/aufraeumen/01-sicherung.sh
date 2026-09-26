##!/bin/bash
# Backup before cleaning up the music archive (AzuraCast, LXC 106 on 192.168.178.163)
# Call:  bash 01-sicherung.sh
set -euo pipefail

DATENSERVER=192.168.178.163
KEY=~/.ssh/id_ed25519
SSH="ssh -o BatchMode=yes -i $KEY root@$DATENSERVER"

STAMP=$(date +%Y%m%d-%H%M%S)
ZIEL_DIR=/root/azuracast-cleanup-$STAMP

$SSH "mkdir -p $ZIEL_DIR"

# The password is stored in the container environment (MYSQL_USER/MYSQL_PASSWORD);
# the wrapper azuracast_db uses the same values.
$SSH 'pct exec 106 -- docker exec azuracast gosu mysql sh -c \
        "mariadb-dump --user=\$MYSQL_USER --password=\$MYSQL_PASSWORD \
         --single-transaction --quick --skip-lock-tables azuracast" \
      | gzip -1 > '"$ZIEL_DIR"'/datenbank.sql.gz'

$SSH "pct exec 106 -- docker exec azuracast gosu mysql azuracast_db -N --raw -e \
        'select concat(pm.playlist_id, char(9), m.path) from station_playlist_media pm \
         join station_media m on m.id = pm.media_id order by pm.playlist_id, m.path' \
        > $ZIEL_DIR/playlist-zuordnungen.tsv"

$SSH "pct exec 106 -- docker exec azuracast gosu mysql azuracast_db -N --raw -e \
        'select concat(id, char(9), path) from station_media order by id' \
        > $ZIEL_DIR/medien-id-path.tsv"

$SSH "du -h $ZIEL_DIR/*; wc -l $ZIEL_DIR/*.tsv"
echo "Backup is located on $DATENSERVER:$ZIEL_DIR"
