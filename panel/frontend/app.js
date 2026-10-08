(function () {
  'use strict';
  var root = document.getElementById('app');
  var csrf = null, me = null, view = 'dashboard', timer = null;

  function h(tag, props) {
    var e = document.createElement(tag), kids = Array.prototype.slice.call(arguments, 2);
    Object.keys(props || {}).forEach(function (k) {
      var v = props[k];
      if (k === 'class') e.className = v;
      else if (k.slice(0, 2) === 'on') e.addEventListener(k.slice(2), v);
      else if (k === 'value') e.value = v;
      else if (v !== false && v != null) e.setAttribute(k, v);
    });
    (function add(list) {
      list.forEach(function (c) {
        if (c == null || c === false) return;
        if (Array.isArray(c)) return add(c);
        e.append(c.nodeType ? c : document.createTextNode(String(c)));
      });
    })(kids);
    return e;
  }

  function api(method, path, body) {
    var o = { method: method, headers: {}, credentials: 'same-origin' };
    if (body !== undefined) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(body); }
    if (method !== 'GET') o.headers['X-CSRF-Token'] = csrf || '';
    return fetch('/api' + path, o).then(function (r) {
      if (r.status === 401 && path.indexOf('/auth/') !== 0) { showLogin(); throw new Error('เซสชันหมดอายุ'); }
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.error || r.statusText);
        return d;
      });
    });
  }

  var toastBox;
  function toast(msg, bad) {
    if (!toastBox) { toastBox = h('div', { class: 'toasts' }); document.body.append(toastBox); }
    var t = h('div', { class: 'toast' + (bad ? ' bad' : '') }, msg);
    toastBox.append(t);
    setTimeout(function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 300); }, 3500);
  }
  function wrapErr(p) { return p.catch(function (e) { toast(e.message, true); }); }

  function fmtBytes(n) { var u = ['B', 'KB', 'MB', 'GB', 'TB'], i = 0; n = Number(n) || 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return n.toFixed(i ? 1 : 0) + ' ' + u[i]; }
  function fmtTime(s) { return s ? new Date(s).toLocaleString('th-TH') : '–'; }
  function fmtUp(s) {
    s = Number(s) || 0;
    var d = Math.floor(s / 86400), hh = Math.floor(s % 86400 / 3600), mm = Math.floor(s % 3600 / 60);
    return d + ' วัน ' + hh + ' ชม. ' + mm + ' นาที';
  }
  function roleTh(r) { return r === 'admin' ? 'ผู้ดูแลระบบ' : (r || ''); }

  var STATUS_TH = { RUNNING: 'ทำงาน', ACTIVE: 'ใช้งาน', STOPPED: 'หยุด', DISABLED: 'ปิดใช้งาน', INACTIVE: 'ไม่ทำงาน', ERROR: 'ผิดพลาด', EXPIRED: 'หมดอายุ', FAILED: 'ล้มเหลว', UNKNOWN: 'ไม่ทราบ' };
  function th(s) { if (s == null || s === '') return ''; return STATUS_TH[String(s).toUpperCase()] || String(s); }
  function stateClass(s) {
    var u = String(s || '').toUpperCase();
    if (/RUNNING|ACTIVE/.test(u)) return 'ok';
    if (/ERROR|FAIL|EXPIRED/.test(u)) return 'bad';
    if (/STOP|DISABL|INACTIVE/.test(u)) return 'warn';
    return 'neutral';
  }
  function badge(state, label) { return h('span', { class: 'badge ' + stateClass(state) }, label != null ? label : th(state)); }

  // ---------------------------------------------------------------- login
  function showLogin(msg) {
    clearInterval(timer);
    var u = h('input', { placeholder: 'ชื่อผู้ใช้', autocomplete: 'username' });
    var p = h('input', { type: 'password', placeholder: 'รหัสผ่าน', autocomplete: 'current-password' });
    var err = h('div', { class: 'err' }, msg || '');
    function go() {
      api('POST', '/auth/login', { username: u.value, password: p.value }).then(function (d) {
        csrf = d.csrf; me = d; render();
      }).catch(function (e) { err.textContent = e.message; });
    }
    p.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
    root.replaceChildren(h('div', { class: 'login-wrap' },
      h('div', { class: 'login card' },
        h('div', { class: 'logo big' }, 'UV'),
        h('h1', {}, 'Unified VPN'),
        h('p', { class: 'mut' }, 'เข้าสู่ระบบเพื่อจัดการแผงควบคุม'),
        h('label', {}, 'ชื่อผู้ใช้'), u,
        h('label', {}, 'รหัสผ่าน'), p,
        h('button', { class: 'primary block', onclick: go }, 'เข้าสู่ระบบ'),
        err)));
  }

  // ---------------------------------------------------------------- shell
  var TABS = [
    { id: 'dashboard', th: 'ภาพรวม' },
    { id: 'users', th: 'ผู้ใช้' },
    { id: 'protocols', th: 'โปรโตคอล' },
    { id: 'services', th: 'บริการ' },
    { id: 'logs', th: 'บันทึกระบบ' },
    { id: 'backups', th: 'สำรองข้อมูล' },
    { id: 'settings', th: 'ตั้งค่า' }
  ];
  function render() {
    clearInterval(timer);
    var nav = h('nav', {}, TABS.map(function (t) {
      return h('button', { class: 'nav-item' + (t.id === view ? ' on' : ''), onclick: function () { view = t.id; render(); } }, t.th);
    }));
    var content = h('main', { class: 'content' });
    root.replaceChildren(h('div', { class: 'layout' },
      h('aside', { class: 'sidebar' },
        h('div', { class: 'brand' }, h('span', { class: 'logo' }, 'UV'),
          h('div', {}, h('b', {}, 'Unified VPN'), h('small', { class: 'mut' }, 'แผงควบคุม'))),
        nav,
        h('div', { class: 'userbox' },
          h('div', { class: 'avatar' }, (me.username || '?').charAt(0).toUpperCase()),
          h('div', { class: 'uinfo' }, h('b', {}, me.username), h('small', { class: 'mut' }, roleTh(me.role))),
          h('button', { class: 'ghost sm', onclick: function () { api('POST', '/auth/logout', {}).then(showLogin); } }, 'ออกจากระบบ'))),
      content));
    ({ dashboard: vDashboard, users: vUsers, protocols: vProtocols, services: vServices, logs: vLogs, backups: vBackups, settings: vSettings })[view](content);
  }

  // ---------------------------------------------------------------- dashboard
  function stat(title, val, sub) { return h('div', { class: 'card stat' }, h('h3', {}, title), h('div', { class: 'big' }, val), h('div', { class: 'mut small' }, sub || '')); }
  function vDashboard(c) {
    c.append(h('h2', {}, 'ภาพรวมระบบ'));
    function load() {
      api('GET', '/dashboard').then(function (d) {
        var uc = d.user_counts || {};
        c.replaceChildren(h('h2', {}, 'ภาพรวมระบบ'),
          h('div', { class: 'grid' },
            stat('ซีพียู', d.cpu_percent + '%', d.cpus + ' คอร์ · โหลด ' + d.load.map(function (x) { return x.toFixed(2); }).join(' ')),
            stat('หน่วยความจำ', d.memory.percent + '%', fmtBytes(d.memory.used) + ' / ' + fmtBytes(d.memory.total)),
            stat('ดิสก์', d.disk.percent + '%', fmtBytes(d.disk.used) + ' / ' + fmtBytes(d.disk.total)),
            stat('เวลาทำงาน', fmtUp(d.uptime), 'ไอพีสาธารณะ ' + (d.public_ip || '?')),
            stat('ออนไลน์', d.online_users, d.online_connections + ' การเชื่อมต่อ'),
            stat('ผู้ใช้', (uc.active || 0) + ' ใช้งาน', (uc.expired || 0) + ' หมดอายุ, ' + (uc.disabled || 0) + ' ปิดใช้งาน'),
            stat('ทราฟฟิก (อินเทอร์เฟซ)', '↓ ' + fmtBytes(d.traffic.rx_bytes), '↑ ' + fmtBytes(d.traffic.tx_bytes) + ' ตั้งแต่เริ่มระบบ')),
          h('div', { class: 'card' }, h('h3', {}, 'โปรโตคอล'), d.protocols.map(function (p) {
            return h('div', { class: 'row' }, h('span', {}, p.label), badge(p.state));
          })),
          h('div', { class: 'card' }, h('h3', {}, 'บริการ'), d.services.map(function (s) {
            return h('div', { class: 'row' }, h('span', {}, s.unit), badge(s.state));
          })));
      }).catch(function (e) { c.replaceChildren(h('h2', {}, 'ภาพรวมระบบ'), h('div', { class: 'err' }, e.message)); });
    }
    load(); timer = setInterval(load, 10000);
  }

  // ---------------------------------------------------------------- users
  function vUsers(c) {
    c.append(h('h2', {}, 'จัดการผู้ใช้'));
    var q = h('input', { placeholder: 'ค้นหา…' });
    var st = h('select', {}, ['', 'active', 'expired', 'disabled'].map(function (s) {
      return h('option', { value: s }, ({ '': 'ทุกสถานะ', active: 'ใช้งาน', expired: 'หมดอายุ', disabled: 'ปิดใช้งาน' })[s]);
    }));
    var pr = h('select', {}, ['', 'ssh', 'openvpn', 'vless', 'vmess', 'trojan', 'reality', 'hysteria2', 'wireguard', 'zivpn'].map(function (s) {
      return h('option', { value: s }, s || 'ทุกโปรโตคอล');
    }));
    var tbody = h('tbody', {});
    function load() {
      api('GET', '/users?q=' + encodeURIComponent(q.value) + '&status=' + st.value + '&protocol=' + pr.value).then(function (list) {
        tbody.replaceChildren.apply(tbody, list.map(function (u) {
          return h('tr', {}, h('td', {}, u.id), h('td', {}, u.username, h('div', { class: 'mut' }, u.note)), h('td', {}, u.protocols.join(', ')),
            h('td', {}, fmtTime(u.created_at)), h('td', {}, fmtTime(u.expires_at)),
            h('td', {}, u.max_connections || 'ไม่จำกัด', h('div', { class: 'mut' }, 'จำนวนอุปกรณ์: ยังไม่บังคับ')), h('td', {}, badge(u.status)),
            h('td', {}, [
              h('button', { class: 'sm', onclick: function () { showConfig(u); } }, 'คอนฟิก'),
              h('button', { class: 'sm', onclick: function () { var d = prompt('ต่ออายุเพิ่มกี่วัน?', '30'); if (d) wrapErr(api('POST', '/users/' + u.id + '/renew', { days: d })).then(load); } }, 'ต่ออายุ'),
              u.status === 'active'
                ? h('button', { class: 'sm', onclick: function () { wrapErr(api('POST', '/users/' + u.id + '/disable', {})).then(load); } }, 'ปิดใช้งาน')
                : h('button', { class: 'sm', onclick: function () { wrapErr(api('POST', '/users/' + u.id + '/enable', {})).then(load); } }, 'เปิดใช้งาน'),
              h('button', { class: 'sm', onclick: function () { var p = prompt('รหัสผ่านใหม่ (ขั้นต่ำ 8 ตัวอักษร)'); if (p) wrapErr(api('POST', '/users/' + u.id + '/reset-password', { password: p })).then(function () { toast('อัปเดตรหัสผ่านแล้ว'); }); } }, 'รหัสผ่าน'),
              h('button', { class: 'sm', onclick: function () { var n = prompt('จำนวนอุปกรณ์สูงสุด (0 = ไม่จำกัด)', u.max_connections); if (n !== null) wrapErr(api('PUT', '/users/' + u.id, { max_connections: n })).then(load); } }, 'จำกัด'),
              h('button', { class: 'danger sm', onclick: function () { if (confirm('ลบผู้ใช้ ' + u.username + ' ?')) wrapErr(api('DELETE', '/users/' + u.id)).then(load); } }, 'ลบ')
            ]));
        }));
      }).catch(function (e) { toast(e.message, true); });
    }
    [q, st, pr].forEach(function (el) { el.addEventListener(el === q ? 'input' : 'change', load); });
    c.append(h('div', { class: 'row' }, q, st, pr, h('button', { class: 'primary', onclick: function () { addUser(load); } }, 'เพิ่มผู้ใช้')),
      h('div', { class: 'card wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['ID', 'ผู้ใช้', 'โปรโตคอล', 'สร้างเมื่อ', 'หมดอายุ', 'อุปกรณ์สูงสุด', 'สถานะ', 'การจัดการ'].map(function (t) { return h('th', {}, t); }))), tbody)));
    load();
  }

  function addUser(done) {
    var f = { username: h('input', { autocomplete: 'off' }), password: h('input', { type: 'text', autocomplete: 'off' }),
      days: h('input', { type: 'number', value: 30, min: 1 }), max_connections: h('input', { type: 'number', value: 1, min: 0 }), note: h('input', {}) };
    var boxes = ['ssh', 'openvpn', 'vless', 'vmess', 'trojan', 'reality', 'hysteria2', 'wireguard', 'zivpn'].map(function (p) {
      var cb = h('input', { type: 'checkbox', value: p }); return h('label', {}, cb, ' ' + p);
    });
    var dlg = h('dialog', {}, h('h3', {}, 'เพิ่มผู้ใช้'),
      h('label', {}, 'ชื่อผู้ใช้'), f.username, h('label', {}, 'รหัสผ่าน (ขั้นต่ำ 8)'), f.password,
      h('label', {}, 'จำนวนวัน'), f.days, h('label', {}, 'จำนวนอุปกรณ์สูงสุด (0 = ไม่จำกัด)'), f.max_connections, h('label', {}, 'หมายเหตุ'), f.note,
      h('label', {}, 'โปรโตคอล'), boxes,
      h('div', { class: 'row' }, h('button', { class: 'primary', onclick: function () {
        var protos = boxes.map(function (l) { return l.firstChild; }).filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
        api('POST', '/users', { username: f.username.value, password: f.password.value, days: f.days.value, max_connections: f.max_connections.value, note: f.note.value, protocols: protos })
          .then(function () { dlg.close(); dlg.remove(); done(); }).catch(function (e) { toast(e.message, true); });
      } }, 'สร้าง'), h('button', { onclick: function () { dlg.close(); dlg.remove(); } }, 'ยกเลิก')));
    document.body.append(dlg); dlg.showModal();
  }

  function showConfig(u) {
    var body = h('div', {}, 'กำลังโหลด…');
    var dlg = h('dialog', {}, h('h3', {}, 'คอนฟิก: ' + u.username), body, h('div', { class: 'row' }, h('button', { onclick: function () { dlg.close(); dlg.remove(); } }, 'ปิด')));
    document.body.append(dlg); dlg.showModal();
    api('GET', '/users/' + u.id + '/share').then(function (items) {
      body.replaceChildren.apply(body, items.map(function (it) {
        var parts = [h('h4', {}, it.protocol.toUpperCase(), ' ', badge(it.account_status))];
        it.links.forEach(function (l) {
          parts.push(h('code', { class: 'link' }, l.url), h('button', { class: 'sm', onclick: function () { navigator.clipboard && navigator.clipboard.writeText(l.url); toast('คัดลอกลิงก์แล้ว'); } }, 'คัดลอก'),
            h('div', {}, h('img', { class: 'qr', alt: 'QR', src: '/api/users/' + u.id + '/qr?protocol=' + it.protocol })));
        });
        it.files.forEach(function (f) {
          parts.push(h('div', {}, h('a', { href: '/api/users/' + u.id + '/config?protocol=' + f.protocol + '&proto=' + (f.proto || '') }, 'ดาวน์โหลด ' + f.label)));
          if (f.protocol === 'wireguard') parts.push(h('div', {}, h('img', { class: 'qr', alt: 'QR', src: '/api/users/' + u.id + '/qr?protocol=wireguard' })));
        });
        Object.keys(it.info || {}).forEach(function (k) { parts.push(h('div', { class: 'mut' }, k + ': ', h('span', {}, String(it.info[k])))); });
        return h('div', { class: 'card' }, parts);
      }));
    }).catch(function (e) { body.replaceChildren(h('div', { class: 'err' }, e.message)); });
  }

  // ---------------------------------------------------------------- protocols / services / logs
  function vProtocols(c) {
    c.append(h('h2', {}, 'โปรโตคอล'));
    api('GET', '/protocols').then(function (list) {
      c.append.apply(c, list.map(function (p) {
        return h('div', { class: 'card' }, h('h3', {}, p.label), badge(p.state),
          h('div', { class: 'mut small' }, JSON.stringify(p.info)),
          Object.keys(p.units).map(function (u) { return h('div', { class: 'row' }, h('span', {}, u), badge(p.units[u])); }),
          p.installed ? '' : h('div', { class: 'mut' }, 'ยังไม่ติดตั้ง — รันคำสั่ง: unified-vpn adapter-install ' + p.name));
      }));
    }).catch(function (e) { toast(e.message, true); });
  }
  function vServices(c) {
    c.append(h('h2', {}, 'บริการระบบ'));
    function load() {
      api('GET', '/services').then(function (list) {
        c.replaceChildren(h('h2', {}, 'บริการระบบ'),
          h('div', { class: 'card wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['ยูนิต', 'สถานะ', 'การจัดการ'].map(function (t) { return h('th', {}, t); }))), h('tbody', {}, list.map(function (s) {
            function act(a, label) { return h('button', { class: 'sm', disabled: s.protected && a !== 'restart', onclick: function () { if (confirm(label + ' ' + s.name + ' ?')) wrapErr(api('POST', '/services/' + s.name + '/' + a, {})).then(load); } }, label); }
            return h('tr', {}, h('td', {}, s.unit), h('td', {}, badge(s.state)), h('td', {}, [act('start', 'เริ่ม'), act('stop', 'หยุด'), act('restart', 'รีสตาร์ท')]));
          })))));
      }).catch(function (e) { toast(e.message, true); });
    }
    load();
  }
  function vLogs(c) {
    c.append(h('h2', {}, 'บันทึกระบบ'));
    var sel = h('select', {}), out = h('pre', {}, ''), lines = h('input', { type: 'number', value: 200, min: 10, max: 1000 });
    function load() { api('GET', '/logs/' + encodeURIComponent(sel.value) + '?lines=' + lines.value).then(function (d) { out.textContent = d.text; }).catch(function (e) { out.textContent = e.message; }); }
    api('GET', '/services').then(function (list) {
      list.forEach(function (s) { sel.append(h('option', { value: s.name }, s.name)); });
      sel.addEventListener('change', load); load();
    });
    c.append(h('div', { class: 'row' }, sel, lines, h('button', { onclick: load }, 'รีเฟรช'), h('span', { class: 'mut small' }, 'รหัสผ่าน / คีย์ / โทเคน ถูกปิดบัง')), out);
  }

  // ---------------------------------------------------------------- backups / settings
  function vBackups(c) {
    c.append(h('h2', {}, 'สำรองข้อมูล'));
    function load() {
      api('GET', '/backups').then(function (list) {
        c.replaceChildren(h('h2', {}, 'สำรองข้อมูล'),
          h('div', { class: 'row' }, h('button', { class: 'primary', onclick: function () { wrapErr(api('POST', '/backups', {})).then(load); } }, 'สร้างข้อมูลสำรอง'),
            h('span', { class: 'mut small' }, 'เข้ารหัสด้วยคีย์ที่ /opt/unified-vpn/config/backup.key — เก็บคีย์นี้ไว้ให้ปลอดภัย')),
          h('div', { class: 'card wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['ชื่อไฟล์', 'ขนาด', 'เวลา', 'การจัดการ'].map(function (t) { return h('th', {}, t); }))), h('tbody', {}, list.map(function (b) {
            return h('tr', {}, h('td', {}, b.name), h('td', {}, fmtBytes(b.size)), h('td', {}, new Date(b.mtime * 1000).toLocaleString('th-TH')), h('td', {}, [
              h('a', { href: '/api/backups/' + b.name }, h('button', { class: 'sm' }, 'ดาวน์โหลด')),
              h('button', { class: 'sm', onclick: function () { if (prompt('พิมพ์ชื่อไฟล์สำรองเพื่อยืนยันการกู้คืน (จะเขียนทับข้อมูลปัจจุบัน):') === b.name) wrapErr(api('POST', '/backups/' + b.name + '/restore', { confirm: b.name })).then(function () { toast('เริ่มกู้คืนแล้ว แผงควบคุมจะรีสตาร์ท'); }); } }, 'กู้คืน'),
              h('button', { class: 'danger sm', onclick: function () { if (confirm('ลบข้อมูลสำรองนี้?')) wrapErr(api('DELETE', '/backups/' + b.name)).then(load); } }, 'ลบ')]));
          })))));
      }).catch(function (e) { c.replaceChildren(h('h2', {}, 'สำรองข้อมูล'), h('div', { class: 'err' }, e.message)); });
    }
    load();
  }
  function vSettings(c) {
    c.append(h('h2', {}, 'ตั้งค่า'));
    var host = h('input', {}), audit = h('pre', {});
    api('GET', '/settings').then(function (s) { host.value = s.host; });
    api('GET', '/audit?limit=100').then(function (l) { audit.textContent = l.map(function (a) { return a.created_at + '  ' + (a.actor || '-') + '  ' + a.action + '  ' + (a.detail || '') + '  ' + (a.ip || ''); }).join('\n'); });
    var cur = h('input', { type: 'password' }), nw = h('input', { type: 'password' });
    c.append(
      h('div', { class: 'card' }, h('h3', {}, 'โฮสต์เซิร์ฟเวอร์ (ใช้ในคอนฟิกไคลเอนต์)'), host,
        h('button', { class: 'primary', onclick: function () { wrapErr(api('PUT', '/settings', { host: host.value })).then(function () { toast('บันทึกแล้ว'); }); } }, 'บันทึก')),
      h('div', { class: 'card' }, h('h3', {}, 'เปลี่ยนรหัสผ่านของฉัน (ขั้นต่ำ 10)'), h('label', {}, 'รหัสผ่านปัจจุบัน'), cur, h('label', {}, 'รหัสผ่านใหม่'), nw,
        h('div', { class: 'row' }, h('button', { onclick: function () { wrapErr(api('POST', '/auth/password', { current: cur.value, new: nw.value })).then(function () { toast('เปลี่ยนรหัสผ่านแล้ว'); cur.value = nw.value = ''; }); } }, 'เปลี่ยนรหัสผ่าน'))),
      h('div', { class: 'card' }, h('h3', {}, 'บันทึกกิจกรรม'), audit));
  }

  api('GET', '/auth/me').then(function (d) { csrf = d.csrf; me = d; render(); }).catch(function () { showLogin(); });
})();
