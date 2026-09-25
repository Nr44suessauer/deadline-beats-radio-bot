#!/bin/bash
# Sicherung vor dem Aufraeumen des Musikarchivs (AzuraCast, LXC 106 auf 192.168.178.163)
# Aufruf:  bash 01-sicherung.sh
set -euo pipefail

DATENSERVER=192.168.178.163
SCHLUESSEL=~/.ssh/id_ed25519
SSH="ssh -o BatchMode=yes -i $SCHLUESSEL root@$DATENSERVER"

STAMP=$(date +%Y%m%d-%H%M%S)
ZIEL_DIR=/root/azuracast-aufraeumen-$STAMP

$SSH "mkdir -p $ZIEL_DIR"

# Das Passwort steht in der Container-Umgebung (MYSQL_USER/MYSQL_PASSWORD);
# der Wrapper azuracast_db nutzt dieselben Werte.
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
        > $ZIEL_DIR/medien-id-pfad.tsv"

$SSH "du -h $ZIEL_DIR/*; wc -l $ZIEL_DIR/*.tsv"
echo "Sicherung liegt auf $DATENSERVER:$ZIEL_DIR"
