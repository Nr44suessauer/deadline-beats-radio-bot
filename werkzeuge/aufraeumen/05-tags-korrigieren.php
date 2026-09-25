<?php
/**
 * Tag-Korrekturen im AzuraCast-Archiv (Stand 2026-09-20).
 *
 * Regeln:
 *  1) Fuehrende Tracknummer aus dem Titel entfernen  ("01 - My Crown" -> "My Crown")
 *  2) Interpret, der nur eine Zahl ist, leeren ("01" -> leer)
 *  3) feat./ft./featuring aus dem Interpreten in den Titel verschieben
 *     ("Modern Talking feat. Eric Singleton" -> Interpret "Modern Talking",
 *      Titel "Sexy Sexy Lover (feat. Eric Singleton)")
 *
 * Nach jeder Aenderung werden "text" und "song_id" genau wie in AzuraCast neu
 * berechnet (App\Entity\Song::getSongHash), damit Wunsch-/Verlaufsdaten stimmig
 * bleiben. Es werden KEINE Dateien angefasst.
 *
 * Aufruf im Container:  DRY=1 php /tmp/tags-korrigieren.php     (nur anzeigen)
 *                       php /tmp/tags-korrigieren.php          (ausfuehren)
 */

require '/var/azuracast/www/vendor/autoload.php';

use App\Entity\Song;

$dry = getenv('DRY') === '1';

$datenbank = getenv('MYSQL_DATABASE') ?: 'azuracast';
$socket = getenv('MYSQL_SOCKET') ?: '/run/mysqld/mysqld.sock';

// Im Container laeuft MariaDB ueber einen Unix-Socket; PHP hat keinen
// Vorgabe-Socket-Pfad, deshalb hier explizit.
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

    // 1) Tracknummer im Titel
    //    Nur wenn nach dem Trenner KEINE Ziffer folgt - sonst wuerde aus
    //    "1.000.000" faelschlich "000.000" und aus "10.000 Light Years"
    //    "000 Light Years". Reine Leerzeichen-Trenner ("99 Luftballons")
    //    werden bewusst nicht angefasst.
    if (preg_match('/^\s*\d{1,2}\s*[.\-_)]\s*(?=\D)(\S.*)$/u', $titel, $m)) {
        $rest = trim($m[1]);
        if (mb_strlen($rest, 'UTF-8') >= 2) {
            $neuTitel = $rest;
            $zaehler['nummer']++;
            $beispiele['nummer'][] = sprintf('%s  ->  %s', $titel, $rest);
            $geaendert = true;
        }
    }

    // 2) Interpret ist nur eine Zahl
    if (preg_match('/^\d{1,3}$/', $interpret)) {
        $neuInterpret = '';
        $zaehler['zahl_interpret']++;
        $beispiele['zahl_interpret'][] = sprintf('%s | %s', $interpret, $neuTitel);
        $geaendert = true;
    }

    // 3) feat. in den Titel
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

    // text und song_id wie in Azuracast neu berechnen
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

echo $dry ? "TROCKENLAUF\n" : "AUSGEFUEHRT\n";
printf("Titel mit Tracknummer bereinigt : %d\n", $zaehler['nummer']);
printf("Interpret war nur eine Zahl     : %d\n", $zaehler['zahl_interpret']);
printf("feat. in den Titel verschoben   : %d\n", $zaehler['feat']);
printf("betroffene Datensaetze          : %d\n", $zaehler['gesamt']);
echo "\nBeispiele:\n";
foreach ($beispiele as $art => $liste) {
    echo "--- $art ---\n";
    foreach (array_slice(array_unique($liste), 0, 8) as $b) {
        echo "   $b\n";
    }
}
