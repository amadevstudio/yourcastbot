cd yourcast
git pull
# git fetch
# git reset --hard origin/master
cd ../
supervisorctl restart yourcast
echo "" > err.log
echo "" > out.log
