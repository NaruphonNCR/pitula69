# Smart Topology – Uptime Monitor → MOPH Notify

ระบบตรวจสอบสถานะ Server / อุปกรณ์เครือข่าย แล้วส่งแจ้งเตือน **Server Down / Online** ผ่าน **MOPH Notify (หมอพร้อม)**
ใช้แทน Uptime Kuma ได้ เขียนด้วย Python ล้วน ไม่ต้องติดตั้งไลบรารีเพิ่ม

## ความสามารถ
- ตรวจได้ 3 แบบ: `icmp` (ping), `tcp` (เช็คพอร์ต เช่น MySQL 3306), `http` (เว็บ/API, เช็ค status code และ keyword ได้)
- กันแจ้งเตือนหลอก: ต้องล้มเหลวติดกัน `retries` ครั้งจึงแจ้ง DOWN
- แจ้ง ONLINE เมื่อกลับมา พร้อมบอกว่าล่มนานเท่าไร
- แจ้งซ้ำทุก `reminder_minutes` นาทีถ้ายังล่มอยู่ (ตั้ง 0 = ไม่แจ้งซ้ำ)
- ข้อความเป็น Flex Message สีแดง/เขียว อ่านง่ายบนมือถือ
- เขียนสถานะลง `status.json` ให้หน้า Dashboard (Smart Topology) ดึงไปแสดงได้

## วิธีติดตั้ง (Linux)
```bash
sudo mkdir -p /opt/moph-monitor && sudo cp monitor.py config.example.json .env.example moph-monitor.service /opt/moph-monitor/
cd /opt/moph-monitor
sudo cp .env.example .env            # ใส่ MOPH_CLIENT_KEY / MOPH_SECRET_KEY
sudo cp config.example.json config.json   # แก้รายการอุปกรณ์

python3 monitor.py --test-notify     # ทดสอบส่งข้อความ
python3 monitor.py --once --dry-run  # ทดสอบตรวจรอบเดียว ไม่ส่งจริง

sudo cp moph-monitor.service /etc/systemd/system/
sudo systemctl enable --now moph-monitor
journalctl -u moph-monitor -f        # ดู log
```

## ตัวอย่างการตั้งค่าอุปกรณ์ (`config.json`)
| ฟิลด์ | ความหมาย |
|---|---|
| `name` | ชื่ออุปกรณ์ที่แสดงในข้อความ |
| `type` | `icmp` / `tcp` / `http` |
| `host`, `port` | สำหรับ icmp / tcp |
| `url`, `expect_status`, `keyword`, `ignore_tls` | สำหรับ http |
| `location` | ตำแหน่ง เช่น Data Center |
| `interval_seconds`, `retries` | กำหนดเฉพาะอุปกรณ์ (ไม่ใส่ = ใช้ค่ากลาง) |
| `enabled` | `false` = ปิดชั่วคราว |

> หมายเหตุ: ไฟล์ `.env` และ `config.json` (มีคีย์และ IP จริง) ถูกใส่ไว้ใน `.gitignore` แล้ว ไม่ถูก push ขึ้น GitHub
