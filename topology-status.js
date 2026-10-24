/*
 * topology-status.js — เชื่อมหน้า Smart Topology เข้ากับ monitor.py
 *
 * วิธีใช้ในหน้า Dashboard:
 *   1) ใส่ <script src="topology-status.js"></script>
 *   2) ใส่ data-monitor-id="<id ใน config.json>" ที่การ์ดอุปกรณ์ เช่น
 *        <div class="node" data-monitor-id="fortigate-100f"> ... </div>
 *      และ (ไม่บังคับ) ใส่ data-monitor-status ไว้ที่ป้ายที่ต้องการให้เปลี่ยนข้อความ
 *        <span data-monitor-status="fortigate-100f"></span>
 *   3) เรียก
 *        TopologyStatus.start("http://10.0.X.X:8088", function (data) {
 *          // (ไม่บังคับ) นำ data.summary ไปอัปเดตการ์ด Online/Offline เอง
 *        });
 *
 * ระบบจะใส่ class "is-up" / "is-down" / "is-unknown" ให้การ์ด
 * แล้วเปลี่ยนข้อความป้ายเป็น ONLINE / LINK DOWN ทุก 10 วินาที
 */
(function (global) {
  var LABEL = { up: "ONLINE", down: "LINK DOWN", unknown: "CHECKING" };

  function apply(data) {
    data.targets.forEach(function (t) {
      document.querySelectorAll('[data-monitor-id="' + CSS.escape(t.id) + '"]').forEach(function (el) {
        el.classList.remove("is-up", "is-down", "is-unknown");
        el.classList.add("is-" + t.status);
        el.title = t.name + " — " + LABEL[t.status] +
          (t.latency_ms != null ? " (" + t.latency_ms + " ms)" : "") + "\n" + t.detail;
      });
      document.querySelectorAll('[data-monitor-status="' + CSS.escape(t.id) + '"]').forEach(function (el) {
        el.textContent = LABEL[t.status];
      });
    });
  }

  function start(baseUrl, onUpdate, intervalMs) {
    var url = String(baseUrl || "").replace(/\/$/, "") + "/api/status";
    function tick() {
      fetch(url, { cache: "no-store" })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (data) { apply(data); if (onUpdate) onUpdate(data, null); })
        .catch(function (err) { if (onUpdate) onUpdate(null, err); });
    }
    tick();
    return setInterval(tick, intervalMs || 10000);
  }

  global.TopologyStatus = { start: start, apply: apply };
})(window);
