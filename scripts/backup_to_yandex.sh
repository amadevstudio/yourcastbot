#!/bin/bash
#
# Yandex.Disk backup script v1.0 by Sergey Lukonin (neblog.info) https://neblog.info/skript-bekapa-na-yandeks-disk
#
# Modified
#
# # # # # # # # # # НАСТРОЙКИ БЕКАПА MYSQL # # # # # # # # # #

# # Сервер БД
# MYSQL_SERVER=mysql.some-server.ru

# # Юзер, под которым будем делать бекап доступных баз, руту mysql обычно доступны все БД, отдельному пользователю обычно доступна БД конкретного проекта
# MYSQL_USER=some-user

# # Пароль пользователя базы данных (Пароль от рута сервера и от рута mysql разные не путайте)
# MYSQL_PASSWORD=some-password

# # # # # # # # # # ОБЩИЕ НАСТРОЙКИ # # # # # # # # # #

# Название проекта, используется в логах и именах архивов
PROJECT='YourcastBot'

# Максимальное количество хранимых на Яндекс.Диске бекапов (0 - хранить все бекапы):
MAX_BACKUPS='14'

# Дата, используется в именах архивов
DATE=`date '+%Y-%m-%d'`

# Work dir is the only positional arg (token comes from the environment so
# it does not show up in `ps`).
HOME_DIR="${1:?work dir required}"
BACKUP_DIR="$HOME_DIR/backup"
DIRS="db"

# Yandex.Disk токен (как получить - см. на neblog.info)
TOKEN="${YANDEX_DISK_BACKUP_TOKEN:-}"

# Имя лог-файла, хранится в директории, указанной в $BACKUP_DIR
LOGFILE='backup.log'

# E-mail для отправки результата выполнения скрипта. Оставьте пустым, если отправлять результаты не требуется.
# sendLog="$2"
sendLog=""

# Отправлять только ошибки (true). Укажите false, если нужно отправлять логи при любом результате выполнения скрипта.
sendLogErrorsOnly='false'

# # # # # # # # # # КОНЕЦ НАСТРОЕК # # # # # # # # # # # # # 
# # # # # # # # ДАЛЬШЕ НИЧЕГО НЕ МЕНЯЕМ! # # # # # # # # # #

if [ -z "$TOKEN" ]; then
    echo "YANDEX_DISK_BACKUP_TOKEN is empty" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
exec 9>"$BACKUP_DIR/backup.lock"
if ! flock -n 9; then
    echo "Backup already running" >&2
    exit 0
fi

function mailing()
{
    if [ ! $sendLog = '' ];then
        if [ "$sendLogErrorsOnly" == true ];
        then
            if echo "$1" | grep -q 'error'
            then   
                echo "$2" | mail -s "$1" $sendLog > /dev/null
            fi
        else
            echo "$2" | mail -s "$1" $sendLog > /dev/null
        fi
    fi
}

function logger()
{
    echo "["`date "+%Y-%m-%d %H:%M:%S"`"] File $BACKUP_DIR: $1" >> $BACKUP_DIR/$LOGFILE
}

function parseJson()
{
    local output
    regex="(\"$1\":[\"]?)([^\",\}]+)([\"]?)"
    [[ $2 =~ $regex ]] && output=${BASH_REMATCH[2]}
    printf '%s\n' "$output"
}

function checkError()
{
    parseJson 'error' "$1"
}

function getUploadUrl()
{
    json_out=$(curl -s -H "Authorization: OAuth $TOKEN" \
        "https://cloud-api.yandex.net:443/v1/disk/resources/upload/?path=app:/${backupName}&overwrite=true")
    json_error=$(checkError "$json_out")
    if [[ $json_error != '' ]];
    then
        logger "$PROJECT - Yandex.Disk error: $json_error"
        mailing "$PROJECT - Yandex.Disk backup error" "ERROR copy file $FILENAME. Yandex.Disk error: $json_error"
        echo ''
    else
        parseJson 'href' "$json_out"
    fi
}

function uploadFile
{
    local json_out
    local uploadUrl
    local http_code
    uploadUrl=$(getUploadUrl | tr -d '\r')
    if [[ $uploadUrl != '' ]];
    then
        json_out=$(mktemp)
        curl_exit=0
        http_code=$(curl -sS -o "$json_out" -w "%{http_code}" \
            --connect-timeout 30 --max-time 3600 \
            -T "$1" -H "Authorization: OAuth $TOKEN" -- "$uploadUrl") || curl_exit=$?
        if [[ "$curl_exit" -ne 0 || ( "$http_code" != 201 && "$http_code" != 200 ) ]];
        then
            logger "$PROJECT - Yandex.Disk upload curl=$curl_exit HTTP $http_code $(tr '\n' ' ' < "$json_out")"
            mailing "$PROJECT - Yandex.Disk backup error" "ERROR copy file $FILENAME. curl=$curl_exit HTTP $http_code"
            rm -f "$json_out"
            return 1
        else
            logger "$PROJECT - Copying file to Yandex.Disk success"
            mailing "$PROJECT - Yandex.Disk backup success" "SUCCESS copy file $FILENAME"
            rm -f "$json_out"
            return 0
        fi
    else
        echo 'Some errors occured. Check log file for detail'
        return 1
    fi
}

function backups_list() {
    # Ищем в директории приложения все файлы бекапов и выводим их названия:
    curl -s -H "Authorization: OAuth $TOKEN" "https://cloud-api.yandex.net:443/v1/disk/resources?path=app:/&sort=created&limit=100" | tr "{},[]" "\n" | grep "name[[:graph:]]*.tar.gz" | cut -d: -f 2 | tr -d '"'
}

function backups_count() {
    backups_list | wc -l
}

function remove_old_backups() {
    bkps=$(backups_count)
    old_bkps=$((bkps - MAX_BACKUPS))
    if [ "$old_bkps" -gt "0" ];then
        logger "Удаляем старые бекапы с Яндекс.Диска ($old_bkps of $bkps)"
        for i in $(seq 1 "$old_bkps"); do
            curl -X DELETE -s -H "Authorization: OAuth $TOKEN" \
                "https://cloud-api.yandex.net:443/v1/disk/resources?path=app:/$(backups_list | awk '(NR == 1)')&permanently=true"
        done
    fi
}

if [ "${FORCE_BACKUP:-}" != 1 ] && [ -f "$BACKUP_DIR/last_success" ] \
    && [ "$(cat "$BACKUP_DIR/last_success")" = "$DATE" ]; then
    logger "--- $PROJECT SKIP BACKUP $DATE (already succeeded today) ---"
    exit 0
fi

logger "--- $PROJECT START BACKUP $DATE ---"
# logger "Выгружаем дампы баз"
# mkdir $BACKUP_DIR/$DATE
# for i in `mysql -h $MYSQL_SERVER -u $MYSQL_USER -p$MYSQL_PASSWORD -e'show databases;' | grep -v information_schema | grep -v Database`;
#     do mysqldump -h $MYSQL_SERVER -u $MYSQL_USER -p$MYSQL_PASSWORD $i > $BACKUP_DIR/$DATE/$i.sql;
# done

# logger "Создаем архив mysql $BACKUP_DIR/$DATE-mysql-$PROJECT.tar.gz"
# tar -czf $BACKUP_DIR/$DATE-mysql-$PROJECT.tar.gz $BACKUP_DIR/$DATE
# rm -rf $BACKUP_DIR/$DATE

logger "Создаем архив каталогов $BACKUP_DIR/$DATE-files-$PROJECT.tar.gz"
find "$BACKUP_DIR" -type f -name "*.gz" -delete
tar -czf $BACKUP_DIR/$DATE-files-$PROJECT.tar.gz -C $HOME_DIR $DIRS

# FILENAME=$DATE-mysql-$PROJECT.tar.gz
# logger "Выгружаем на Яндекс.Диск архив mysql $BACKUP_DIR/$DATE-mysql-$PROJECT.tar.gz"
# backupName=$DATE-mysql-$PROJECT.tar.gz
# uploadFile $BACKUP_DIR/$DATE-mysql-$PROJECT.tar.gz

FILENAME=$DATE-files-$PROJECT.tar.gz
logger "Выгружаем на Яндекс.Диск архив с файлами $BACKUP_DIR/$DATE-files-$PROJECT.tar.gz"
backupName=$DATE-files-$PROJECT.tar.gz
uploadFile $BACKUP_DIR/$DATE-files-$PROJECT.tar.gz
upload_status=$?

if [ $upload_status -eq 0 ]; then
    logger "Удаляем локальный архив после успешной заливки"
    rm -f "$BACKUP_DIR/$FILENAME"
    echo "$DATE" > "$BACKUP_DIR/last_success"
    if [ $MAX_BACKUPS -gt 0 ]; then
        remove_old_backups
    fi
else
    logger "Локальный архив оставлен после ошибки: $BACKUP_DIR/$FILENAME"
fi

logger "Завершение скрипта бекапа"
exit $upload_status
