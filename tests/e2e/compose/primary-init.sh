#!/bin/sh
# primary 초기화(compose.e2e.yaml): replica 가 GTID 자동 위치로 붙을 복제 계정.
# 실행 권한에 따라 source 되기도 실행되기도 하므로(/mnt/c 는 0777) 헬퍼 대신 mysql 클라이언트를 쓴다.
mysql --protocol=socket -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE USER 'repl'@'%' IDENTIFIED BY '${MYSQL_ROOT_PASSWORD}';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';
SQL
