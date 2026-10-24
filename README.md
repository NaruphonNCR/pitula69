# Smart Topology – Uptime Monitor → MOPH Notify

ระบบตรวจสอบสถานะ Server / อุปกรณ์เครือข่าย แล้วส่งแจ้งเตือน **Server Down / Online** ผ่าน **MOPH Notify (หมอพร้อม)**
ใช้แทน Uptime Kuma ได้ เขียนด้วย Python ล้วน ไม่ต้องติดตั้งไลบรารีเพิ่ม

## ความสามารถ
- ตรวจได้ 3 แบบ: `icmp` (ping), `tcp` (เช็คพอร์ต เช่น MySQL 3306), `http` (เว็บ/API, เช็ค status code และ keyword ได้)
- กันแจ้งเตือนหลอก: ต้องล้มเหลวติดกัน `retries` ครั้งจึงแจ้ง DOWN
- แจ้ง ONLINE เมื่อกลับมา พร้อมบอกว่าล่มนานเท่าไร
- แจ้งซ้ำทุก `reminder_minutes` นาทีถ้ายังล่มอยู่ (ตั้ง 0 = ไม่แจ้งซ้ำ)
- ข้อความเป็น Flex Message สีแดง/เขียว อ่านง่ายบนมือถือ
- มีหน้าเว็บแสดงสถานะในตัว (`status.html`) และ API `GET /api/status` ให้หน้า Smart Topology ดึงไปแสดงได้
- เขียนสถานะลงไฟล์ `status.json` ด้วย (ถ้าตั้งค่า `status_file`)

## วิธีติดตั้ง (Linux)
```bash
sudo mkdir -p /opt/moph-monitor && sudo cp monitor.py status.html topology-status.js config.example.json .env.example moph-monitor.service /opt/moph-monitor/
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
| `id` | รหัสอุปกรณ์ ใช้ผูกกับการ์ดบนหน้า Dashboard (ไม่ใส่ = ใช้ `name`) |

## หน้าแสดงสถานะ และการเชื่อมกับ Dashboard
ตั้ง `"http_port": 8088` ใน `config.json` แล้วเปิด `http://<ip-เครื่อง-monitor>:8088/` จะเห็นหน้าสถานะ
(การ์ด Online / Offline / Availability, ค้นหา, กรองเฉพาะเครื่องที่ล่ม, รองรับมือถือและโหมดมืด)

ข้อมูล JSON ดึงได้ที่ `http://<ip>:8088/api/status` (เปิด CORS แล้ว เรียกจากหน้าเว็บอื่นได้)

ถ้าจะให้หน้า **Smart Topology** เปลี่ยนป้าย LINK DOWN / ONLINE ตามจริง:
```html
<script src="topology-status.js"></script>
<div class="node" data-monitor-id="fortigate-100f">
  FortiGate 100F <span data-monitor-status="fortigate-100f"></span>
</div>
<script>
  TopologyStatus.start("http://10.0.X.X:8088", function (data) {
    if (!data) return;                          // เชื่อมต่อไม่ได้
    document.querySelector("#online").textContent = data.summary.up;
    document.querySelector("#offline").textContent = data.summary.down;
  });
</script>
<style>
  .node.is-down { outline: 2px solid #dc2626; }
  .node.is-up   { outline: 2px solid #16a34a; }
</style>
```
> ควรเปิดพอร์ต 8088 เฉพาะในวงแลนโรงพยาบาลเท่านั้น

> หมายเหตุ: ไฟล์ `.env` และ `config.json` (มีคีย์และ IP จริง) ถูกใส่ไว้ใน `.gitignore` แล้ว ไม่ถูก push ขึ้น GitHub
