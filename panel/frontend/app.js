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
      if (r.status === 401 && path.indexOf('/auth/') !== 0) { showLogin(); throw new Error('session expired'); }
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.error || r.statusText);
        return d;
      });
    });
  }
  function toast(msg, bad) { alert((bad ? 'Error: ' : '') + msg); }
  function wrapErr(p) { return p.catch(function (e) { toast(e.message, true); }); }
  function fmtBytes(n) { var u = ['B', 'KB', 'MB', 'GB', 'TB'], i = 0; n = Number(n) || 0; while (n >= 1024 && i < 4) { n /= 1024; i++; } return n.toFixed(i ? 1 : 0) + ' ' + u[i]; }
  function fmtTime(s) { return s ? new Date(s).toLocaleString() : '-'; }
  function fmtUp(s) { var d = Math.floor(s / 86400), hh = Math.floor(s % 86400 / 3600); return d + 'd ' + hh + 'h'; }
  function badge(t) { return h('span', { class: 'badge ' + t }, t); }

  // ---------------------------------------------------------------- login
  function showLogin(msg) {
    clearInterval(timer);
    var u = h('input', { placeholder: 'Username', autocomplete: 'username' });
    var p = h('input', { type: 'password', placeholder: 'Password', autocomplete: 'current-password' });
    var err = h('div', { class: 'err' }, msg || '');
    function go() {
      api('POST', '/auth/login', { username: u.value, password: p.value }).then(function (d) {
        csrf = d.csrf; me = d; render();
      }).catch(function (e) { err.textContent = e.message; });
    }
    p.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
    root.replaceChildren(h('div', { class: 'login card' }, h('h2', {}, 'Unified VPN Panel'),
      h('label', {}, 'Username'), u, h('label', {}, 'Password'), p, h('div', { class: 'row' }, h('button', { class: 'primary', onclick: go }, 'Login')), err));
  }

  // ---------------------------------------------------------------- shell
  var TABS = ['dashboard', 'users', 'protocols', 'services', 'logs', 'backups', 'settings'];
  function render() {
    clearInterval(timer);
    var nav = h('nav', {}, TABS.map(function (t) {
      return h('button', { class: t === view ? 'on' : '', onclick: function () { view = t; render(); } }, t[0].toUpperCase() + t.slice(1));
    }));
    var content = h('main', {});
    root.replaceChildren(h('header', {}, h('b', {}, 'Unified VPN'), nav, h('span', { class: 'mut' }, me.username + ' (' + me.role + ')'),
      h('button', { onclick: function () { api('POST', '/auth/logout', {}).then(showLogin); } }, 'Logout')), content);
    ({ dashboard: vDashboard, users: vUsers, protocols: vProtocols, services: vServices, logs: vLogs, backups: vBackups, settings: vSettings })[view](content);
  }

  // ---------------------------------------------------------------- dashboard
  function stat(title, val, sub) { return h('div', { class: 'card' }, h('h3', {}, title), h('div', { class: 'big' }, val), h('div', { class: 'mut' }, sub || '')); }
  function vDashboard(c) {
    function load() {
      api('GET', '/dashboard').then(function (d) {
        var uc = d.user_counts || {};
        c.replaceChildren(
          h('div', { class: 'grid' },
            stat('CPU', d.cpu_percent + '%', d.cpus + ' cores, load ' + d.load.map(function (x) { return x.toFixed(2); }).join(' ')),
            stat('RAM', d.memory.percent + '%', fmtBytes(d.memory.used) + ' / ' + fmtBytes(d.memory.total)),
            stat('Disk', d.disk.percent + '%', fmtBytes(d.disk.used) + ' / ' + fmtBytes(d.disk.total)),
            stat('Uptime', fmtUp(d.uptime), 'Public IP ' + (d.public_ip || '?')),
            stat('Online', d.online_users, d.online_connections + ' connections'),
            stat('Users', (uc.active || 0) + ' active', (uc.expired || 0) + ' expired, ' + (uc.disabled || 0) + ' disabled'),
            stat('Traffic (iface)', '↓ ' + fmtBytes(d.traffic.rx_bytes), '↑ ' + fmtBytes(d.traffic.tx_bytes) + ' since boot')),
          h('div', { class: 'card' }, h('h3', {}, 'Protocols'), d.protocols.map(function (p) {
            return h('div', { class: 'row' }, h('span', {}, p.label), badge(p.state));
          })),
          h('div', { class: 'card' }, h('h3', {}, 'Services'), d.services.map(function (s) {
            return h('div', { class: 'row' }, h('span', {}, s.unit), badge(s.state));
          })));
      }).catch(function (e) { c.replaceChildren(h('div', { class: 'err' }, e.message)); });
    }
    load(); timer = setInterval(load, 10000);
  }

  // ---------------------------------------------------------------- users
  function vUsers(c) {
    var q = h('input', { placeholder: 'Search…' });
    var st = h('select', {}, ['', 'active', 'expired', 'disabled'].map(function (s) { return h('option', { value: s }, s || 'All status'); }));
    var pr = h('select', {}, ['', 'ssh', 'openvpn', 'vless', 'vmess', 'trojan', 'reality', 'hysteria2', 'wireguard', 'zivpn'].map(function (s) { return h('option', { value: s }, s || 'All protocols'); }));
    var tbody = h('tbody', {});
    function load() {
      api('GET', '/users?q=' + encodeURIComponent(q.value) + '&status=' + st.value + '&protocol=' + pr.value).then(function (list) {
        tbody.replaceChildren.apply(tbody, list.map(function (u) {
          return h('tr', {}, h('td', {}, u.id), h('td', {}, u.username, h('div', { class: 'mut' }, u.note)), h('td', {}, u.protocols.join(', ')),
            h('td', {}, fmtTime(u.created_at)), h('td', {}, fmtTime(u.expires_at)),
            h('td', {}, u.max_connections || '∞', h('div', { class: 'mut' }, 'devices: not enforced')), h('td', {}, badge(u.status)),
            h('td', {}, [
              h('button', { onclick: function () { showConfig(u); } }, 'Config'),
              h('button', { onclick: function () { var d = prompt('Renew by how many days?', '30'); if (d) wrapErr(api('POST', '/users/' + u.id + '/renew', { days: d })).then(load); } }, 'Renew'),
              u.status === 'active'
                ? h('button', { onclick: function () { wrapErr(api('POST', '/users/' + u.id + '/disable', {})).then(load); } }, 'Disable')
                : h('button', { onclick: function () { wrapErr(api('POST', '/users/' + u.id + '/enable', {})).then(load); } }, 'Enable'),
              h('button', { onclick: function () { var p = prompt('New password (min 8 chars)'); if (p) wrapErr(api('POST', '/users/' + u.id + '/reset-password', { password: p })).then(function () { toast('Password updated'); }); } }, 'Password'),
              h('button', { onclick: function () { var n = prompt('Max connections (0 = unlimited)', u.max_connections); if (n !== null) wrapErr(api('PUT', '/users/' + u.id, { max_connections: n })).then(load); } }, 'Limit'),
              h('button', { class: 'danger', onclick: function () { if (confirm('Delete ' + u.username + '?')) wrapErr(api('DELETE', '/users/' + u.id)).then(load); } }, 'Delete')
            ]));
        }));
      }).catch(function (e) { toast(e.message, true); });
    }
    [q, st, pr].forEach(function (el) { el.addEventListener(el === q ? 'input' : 'change', load); });
    c.replaceChildren(h('div', { class: 'row' }, q, st, pr, h('button', { class: 'primary', onclick: function () { addUser(load); } }, '+ Add user')),
      h('div', { class: 'card wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['ID', 'User', 'Protocols', 'Created', 'Expires', 'Max conn.', 'Status', 'Actions'].map(function (t) { return h('th', {}, t); }))), tbody)));
    load();
  }

  function addUser(done) {
    var f = { username: h('input', { autocomplete: 'off' }), password: h('input', { type: 'text', autocomplete: 'off' }),
      days: h('input', { type: 'number', value: 30, min: 1 }), max_connections: h('input', { type: 'number', value: 1, min: 0 }), note: h('input', {}) };
    var boxes = ['ssh', 'openvpn', 'vless', 'vmess', 'trojan', 'reality', 'hysteria2', 'wireguard', 'zivpn'].map(function (p) {
      var cb = h('input', { type: 'checkbox', value: p }); return h('label', {}, cb, ' ' + p);
    });
    var dlg = h('dialog', {}, h('h3', {}, 'Add user'),
      h('label', {}, 'Username'), f.username, h('label', {}, 'Password (min 8)'), f.password,
      h('label', {}, 'Days'), f.days, h('label', {}, 'Max connections (0 = unlimited)'), f.max_connections, h('label', {}, 'Note'), f.note,
      h('label', {}, 'Protocols'), boxes,
      h('div', { class: 'row' }, h('button', { class: 'primary', onclick: function () {
        var protos = boxes.map(function (l) { return l.firstChild; }).filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
        api('POST', '/users', { username: f.username.value, password: f.password.value, days: f.days.value, max_connections: f.max_connections.value, note: f.note.value, protocols: protos })
          .then(function () { dlg.close(); dlg.remove(); done(); }).catch(function (e) { toast(e.message, true); });
      } }, 'Create'), h('button', { onclick: function () { dlg.close(); dlg.remove(); } }, 'Cancel')));
    document.body.append(dlg); dlg.showModal();
  }

  function showConfig(u) {
    var body = h('div', {}, 'Loading…');
    var dlg = h('dialog', {}, h('h3', {}, 'Config: ' + u.username), body, h('div', { class: 'row' }, h('button', { onclick: function () { dlg.close(); dlg.remove(); } }, 'Close')));
    document.body.append(dlg); dlg.showModal();
    api('GET', '/users/' + u.id + '/share').then(function (items) {
      body.replaceChildren.apply(body, items.map(function (it) {
        var parts = [h('h4', {}, it.protocol.toUpperCase(), ' ', badge(it.account_status))];
        it.links.forEach(function (l) {
          parts.push(h('code', { class: 'link' }, l.url), h('button', { onclick: function () { navigator.clipboard && navigator.clipboard.writeText(l.url); } }, 'Copy'),
            h('div', {}, h('img', { class: 'qr', alt: 'QR', src: '/api/users/' + u.id + '/qr?protocol=' + it.protocol })));
        });
        it.files.forEach(function (f) {
          parts.push(h('div', {}, h('a', { href: '/api/users/' + u.id + '/config?protocol=' + f.protocol + '&proto=' + (f.proto || '') }, '⬇ ' + f.label)));
          if (f.protocol === 'wireguard') parts.push(h('div', {}, h('img', { class: 'qr', alt: 'QR', src: '/api/users/' + u.id + '/qr?protocol=wireguard' })));
        });
        Object.keys(it.info || {}).forEach(function (k) { parts.push(h('div', { class: 'mut' }, k + ': ', h('span', {}, String(it.info[k])))); });
        return h('div', { class: 'card' }, parts);
      }));
    }).catch(function (e) { body.replaceChildren(h('div', { class: 'err' }, e.message)); });
  }

  // ---------------------------------------------------------------- protocols / services / logs
  function vProtocols(c) {
    api('GET', '/protocols').then(function (list) {
      c.replaceChildren.apply(c, list.map(function (p) {
        return h('div', { class: 'card' }, h('h3', {}, p.label), badge(p.state),
          h('div', { class: 'mut' }, JSON.stringify(p.info)),
          Object.keys(p.units).map(function (u) { return h('div', { class: 'row' }, h('span', {}, u), badge(p.units[u])); }),
          p.installed ? '' : h('div', { class: 'mut' }, 'Not installed. Run: unified-vpn adapter-install ' + p.name));
      }));
    }).catch(function (e) { toast(e.message, true); });
  }
  function vServices(c) {
    function load() {
      api('GET', '/services').then(function (list) {
        c.replaceChildren(h('div', { class: 'card wrap' }, h('table', {}, list.map(function (s) {
          function act(a) { return h('button', { disabled: s.protected && a !== 'restart', onclick: function () { if (confirm(a + ' ' + s.name + '?')) wrapErr(api('POST', '/services/' + s.name + '/' + a, {})).then(load); } }, a); }
          return h('tr', {}, h('td', {}, s.unit), h('td', {}, badge(s.state)), h('td', {}, [act('start'), act('stop'), act('restart')]));
        }))));
      }).catch(function (e) { toast(e.message, true); });
    }
    load();
  }
  function vLogs(c) {
    var sel = h('select', {}), out = h('pre', {}, ''), lines = h('input', { type: 'number', value: 200, min: 10, max: 1000 });
    function load() { api('GET', '/logs/' + encodeURIComponent(sel.value) + '?lines=' + lines.value).then(function (d) { out.textContent = d.text; }).catch(function (e) { out.textContent = e.message; }); }
    api('GET', '/services').then(function (list) {
      list.forEach(function (s) { sel.append(h('option', { value: s.name }, s.name)); });
      sel.addEventListener('change', load); load();
    });
    c.replaceChildren(h('div', { class: 'row' }, sel, lines, h('button', { onclick: load }, 'Refresh'), h('span', { class: 'mut' }, 'passwords / keys / tokens are redacted')), out);
  }

  // ---------------------------------------------------------------- backups / settings
  function vBackups(c) {
    function load() {
      api('GET', '/backups').then(function (list) {
        c.replaceChildren(h('div', { class: 'row' }, h('button', { class: 'primary', onclick: function () { wrapErr(api('POST', '/backups', {})).then(load); } }, 'Create backup'),
          h('span', { class: 'mut' }, 'Encrypted with the key in /opt/unified-vpn/config/backup.key - store that key safely.')),
          h('div', { class: 'card wrap' }, h('table', {}, list.map(function (b) {
            return h('tr', {}, h('td', {}, b.name), h('td', {}, fmtBytes(b.size)), h('td', {}, new Date(b.mtime * 1000).toLocaleString()), h('td', {}, [
              h('a', { href: '/api/backups/' + b.name }, h('button', {}, 'Download')),
              h('button', { class: 'danger', onclick: function () { if (prompt('Type the backup name to confirm RESTORE (overwrites current data):') === b.name) wrapErr(api('POST', '/backups/' + b.name + '/restore', { confirm: b.name })).then(function () { toast('Restore started. Panel will restart.'); }); } }, 'Restore'),
              h('button', { onclick: function () { if (confirm('Delete backup?')) wrapErr(api('DELETE', '/backups/' + b.name)).then(load); } }, 'Delete')]));
          }))));
      }).catch(function (e) { c.replaceChildren(h('div', { class: 'err' }, e.message)); });
    }
    load();
  }
  function vSettings(c) {
    var host = h('input', {}), audit = h('pre', {});
    api('GET', '/settings').then(function (s) { host.value = s.host; });
    api('GET', '/audit?limit=100').then(function (l) { audit.textContent = l.map(function (a) { return a.created_at + '  ' + (a.actor || '-') + '  ' + a.action + '  ' + (a.detail || '') + '  ' + (a.ip || ''); }).join('\n'); });
    var cur = h('input', { type: 'password' }), nw = h('input', { type: 'password' });
    c.replaceChildren(
      h('div', { class: 'card' }, h('h3', {}, 'Server host (used in client configs)'), host,
        h('button', { class: 'primary', onclick: function () { wrapErr(api('PUT', '/settings', { host: host.value })).then(function () { toast('Saved'); }); } }, 'Save')),
      h('div', { class: 'card' }, h('h3', {}, 'Change my password (min 10)'), h('label', {}, 'Current'), cur, h('label', {}, 'New'), nw,
        h('div', { class: 'row' }, h('button', { onclick: function () { wrapErr(api('POST', '/auth/password', { current: cur.value, new: nw.value })).then(function () { toast('Password changed'); cur.value = nw.value = ''; }); } }, 'Change'))),
      h('div', { class: 'card' }, h('h3', {}, 'Audit log'), audit));
  }

  api('GET', '/auth/me').then(function (d) { csrf = d.csrf; me = d; render(); }).catch(function () { showLogin(); });
})();
