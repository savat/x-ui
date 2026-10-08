# managed by unified-vpn installer - regenerate with install.sh, do not hand-edit
server {
    listen 80@DEFAULT@;
    listen [::]:80@DEFAULT@;
    server_name @SERVER_NAME@;

    location /.well-known/acme-challenge/ { root /var/www/html; }
    include /etc/unified-vpn/nginx-http.d/*.conf;      # plain-WS locations written by adapters
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2@DEFAULT@;
    listen [::]:443 ssl http2@DEFAULT@;
    server_name @SERVER_NAME@;

    ssl_certificate     @CERT@;
    ssl_certificate_key @KEY@;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:uvpn:10m;
    @HSTS@

    include /etc/unified-vpn/nginx.d/*.conf;           # WS/TLS locations written by adapters

    location / {
        proxy_pass http://127.0.0.1:@PANEL_PORT@;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 1m;
    }
}
