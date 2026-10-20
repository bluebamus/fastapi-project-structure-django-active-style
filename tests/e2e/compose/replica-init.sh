#!/bin/sh
# replica 초기화(compose.e2e.yaml): primary 에 GTID 자동 위치로 붙는다. primary 의 앱 DB·계정은 복제로 넘어온다.
# 복제 설정은 mysql.slave_master_info 에 남아 진짜 서버가 뜰 때 자동으로 다시 시작된다.
mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CHANGE REPLICATION SOURCE TO
  SOURCE_HOST='mysql-primary', SOURCE_PORT=3306,
  SOURCE_USER='repl', SOURCE_PASSWORD='${MYSQL_ROOT_PASSWORD}',
  SOURCE_AUTO_POSITION=1, GET_SOURCE_PUBLIC_KEY=1;
START REPLICA;
SQL
