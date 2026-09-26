<?php
/**
 * Tag corrections in the AzuraCast archive (as of 2026-09-20).
 *
 * Rules:
 *  1) Remove the leading track number from the title  ("01 - My Crown" -> "My Crown")
 *  2) Empty an artist that is only a number ("01" -> empty)
 *  3) Move feat./ft./featuring from the artist into the title
 *     ("Modern Talking feat. Eric Singleton" -> artist "Modern Talking",
 *      title "Sexy Sexy Lover (feat. Eric Singleton)")
 *
 * After every change, "text" and "song_id" are recomputed exactly as in AzuraCast
 * (App\Entity\Song::getSongHash) so that request/history data stays consistent.
 * NO files are touched.
 *
 * Call in the container:  DRY=1 php /tmp/tags-korrigieren.php     (display only)
 *                         php /tmp/tags-korrigieren.php          (execute)
 */

require '/var/azuracast/www/vendor/autoload.php';

use App\Entity\Song;

$dry = getenv('DRY') === '1';

$datenbank = getenv('MYSQL_DATABASE') ?: 'azuracast';
$socket = getenv('MYSQL_SOCKET') ?: '/run/mysqld/mysqld.sock';

// In the container MariaDB runs over a Unix socket; PHP has no
// default socket path, so it is given explicitly here.
$dsn = file_exists($socket)
    ? sprintf('mysql:unix_socket=%s;dbname=%s;charset=utf8mb4', $socket, $datenbank)
    : sprintf(
        'mysql:host=%s;port=%s;dbname=%s;charset=utf8mb4',
        getenv('MYSQL_HOST') ?: '127.0.0.1',
        getenv('MYSQL_PORT') ?: '3306',
        $datenbank
    );

$pdo = new PDO(
    $dsn,
    getenv('MYSQL_USER') ?: 'azuracast',
    getenv('MYSQL_PASSWORD') ?: 'azur4c457',
    [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
);

$zeilen = $pdo->query('SELECT id, title, artist, album, path FROM station_media');

$zaehler = ['nummer' => 0, 'zahl_interpret' => 0, 'feat' => 0, 'gesamt' => 0];
$beispiele = [];

$update = $pdo->prepare(
    'UPDATE station_media SET title = ?, artist = ?, text = ?, song_id = ? WHERE id = ?'
);

if (!$dry) {
    if (!getenv('OHNE_TRANSAKTION')) {
        $pdo->beginTransaction();
    }
}

foreach ($zeilen as $r) {
    $titel = (string)$r['title'];
    $interpret = $r['artist'] === null ? '' : (string)$r['artist'];
    $album = (string)$r['album'];
    $neuTitel = $titel;
    $neuInterpret = $interpret;
    $geaendert = false;

    // 1) track number in the title
    //    Only if NO digit follows the separator - otherwise "1.000.000" would
    //    wrongly become "000.000" and "10.000 Light Years" would become
    //    "000 Light Years". Plain space separators ("99 Luftballons")
    //    are deliberately left alone.
    if (preg_match('/^\s*\d{1,2}\s*[.\-_)]\s*(?=\D)(\S.*)$/u', $titel, $m)) {
        $rest = trim($m[1]);
        if (mb_strlen($rest, 'UTF-8') >= 2) {
            $neuTitel = $rest;
            $zaehler['nummer']++;
            $beispiele['nummer'][] = sprintf('%s  ->  %s', $titel, $rest);
            $geaendert = true;
        }
    }

    // 2) artist is only a number
    if (preg_match('/^\d{1,3}$/', $interpret)) {
        $neuInterpret = '';
        $zaehler['zahl_interpret']++;
        $beispiele['zahl_interpret'][] = sprintf('%s | %s', $interpret, $neuTitel);
        $geaendert = true;
    }

    // 3) feat. into the title
    if (preg_match('/^(.+?)\s+(feat\.?|ft\.?|featuring)\s+(.+)$/iu', $neuInterpret, $m)) {
        $haupt = trim($m[1]);
        $gast = trim($m[3]);
        if (mb_strlen($haupt, 'UTF-8') >= 2 && mb_strlen($gast, 'UTF-8') >= 2) {
            $neuInterpret = $haupt;
            if (mb_stripos($neuTitel, $gast) === false) {
                $neuTitel .= ' (feat. ' . $gast . ')';
            }
            $zaehler['feat']++;
            $beispiele['feat'][] = sprintf('%s | %s', $haupt, $neuTitel);
            $geaendert = true;
        }
    }

    if (!$geaendert) {
        continue;
    }

    $zaehler['gesamt']++;

    // recompute text and song_id as in AzuraCast
    $teile = array_filter([trim($neuInterpret), trim($album), trim($neuTitel)]);
    $text = implode(' - ', $teile);
    $songId = $text !== '' ? Song::getSongHash($text) : Song::OFFLINE_SONG_ID;

    if (!$dry) {
        $update->execute([$neuTitel, $neuInterpret === '' ? null : $neuInterpret, $text, $songId, $r['id']]);
    }
}

if (!$dry && !getenv('OHNE_TRANSAKTION')) {
    $pdo->commit();
}

echo $dry ? "DRY RUN\n" : "EXECUTED\n";
printf("titles cleaned of track number  : %d\n", $zaehler['nummer']);
printf("artist was only a number        : %d\n", $zaehler['zahl_interpret']);
printf("feat. moved into the title      : %d\n", $zaehler['feat']);
printf("affected records                : %d\n", $zaehler['gesamt']);
echo "\nExamples:\n";
foreach ($beispiele as $art => $liste) {
    echo "--- $art ---\n";
    foreach (array_slice(array_unique($liste), 0, 8) as $b) {
        echo "   $b\n";
    }
}
