Since you don't have the `sqlite3` CLI installed on your Windows host, you can run the queries **inside the running Docker container** (which has the SQLite engine and database mounted). 

Open your terminal (PowerShell or Command Prompt) in the `eric-robotics/ros2-jazzy` directory and run these commands:

### 1. View all tables in the database
```bash
docker exec -it ros2-bridge sqlite3 /data/local_robot.db "SELECT name FROM sqlite_master WHERE type='table';"
```

### 2. View the latest 5 GPS coordinates
```bash
docker exec -it ros2-bridge sqlite3 /data/local_robot.db "SELECT * FROM telemetry_gps ORDER BY id DESC LIMIT 5;"
```

### 3. View the latest 5 Odometry readings (Speed, Heading, Coordinates)
```bash
docker exec -it ros2-bridge sqlite3 /data/local_robot.db "SELECT * FROM telemetry_odom ORDER BY id DESC LIMIT 5;"
```

### 4. View the latest 5 System Logs
```bash
docker exec -it ros2-bridge sqlite3 /data/local_robot.db "SELECT * FROM system_logs ORDER BY id DESC LIMIT 5;"
```

---

### 5. Open Interactive Database Shell
If you want to run queries interactively (just like a SQL console), start the interactive shell using:
```bash
docker exec -it ros2-bridge sqlite3 /data/local_robot.db
```
Inside the interactive prompt, you can run:
*   Show tables: `.tables`
*   Show schema of a table: `.schema telemetry_gps`
*   Query data: `SELECT * FROM telemetry_gps LIMIT 10;`
*   Exit the shell: `.exit`