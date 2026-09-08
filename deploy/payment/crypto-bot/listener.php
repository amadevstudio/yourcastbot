<?php
declare(strict_types=1);

require __DIR__ . '/../../config.php';

error_reporting(0);
ini_set('display_errors', '0');

$body = file_get_contents('php://input');
$body_b64 = base64_encode($body === false ? '' : $body);

$sig = '';
foreach ($_SERVER as $key => $value) {
    if (strtoupper($key) === 'HTTP_CRYPTO_PAY_API_SIGNATURE') {
        $sig = (string)$value;
        break;
    }
}
$headers = $sig === ''
    ? new stdClass()
    : array('Crypto-Pay-Api-Signature' => $sig);
$headers_b64 = base64_encode(json_encode($headers));

$python = $bot_path . '/venv/bin/python';
$script = $bot_path . '/scripts/payment/cryptoBot.py';
if (!is_file($python) || !is_file($script)) {
    http_response_code(500);
    exit;
}

$cmd = array($python, $script, $bot_path, $body_b64, $headers_b64);
$desc = array(
    1 => array('pipe', 'w'),
    2 => array('pipe', 'w'),
);
$proc = proc_open($cmd, $desc, $pipes, $bot_path, null, array('bypass_shell' => true));
if (!is_resource($proc)) {
    http_response_code(500);
    exit;
}
$out = stream_get_contents($pipes[1]);
fclose($pipes[1]);
fclose($pipes[2]);
proc_close($proc);

$ok = preg_replace('/\s+/', '', (string)$out) === 'OK';
http_response_code($ok ? 200 : 400);
if ($ok) {
    echo 'OK';
}
