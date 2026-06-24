# U2Magic + u2_scripts

## docker-compose.yml 示例

```yaml
services:
  init:
    image: alpine:3.21
    restart: "no"
    command:
      - /bin/sh
      - -c
      - |
        set -eu
        mkdir -p /runtime/u2magic/data/config /runtime/u2magic/data/cookie
        mkdir -p /runtime/u2magic/data/db /runtime/u2magic/data/xml
        mkdir -p /runtime/u2magic/logs /runtime/u2_scripts/logs
        test -f /runtime/u2magic/data/config/config.json ||
          cp /templates/u2magic/config.json /runtime/u2magic/data/config/config.json
        test -f /runtime/u2_scripts/webui_config.json ||
          cp /templates/u2_scripts/webui_config.json /runtime/u2_scripts/webui_config.json
    volumes:
      - ./config-templates:/templates:ro
      - ./runtime:/runtime

  u2magic:
    build:
      context: ./u2magic/deploy
    image: u2magic-local:latest
    restart: unless-stopped
    depends_on:
      init:
        condition: service_completed_successfully
    expose:
      - "18080"
    volumes:
      - ./runtime/u2magic/logs:/data/u2Magic/logs
      - ./runtime/u2magic/data:/data/u2
      - ./config-templates/u2magic/application-base.yml:/data/u2Magic/config/application-base.yml:ro
    extra_hosts:
      - "u2.dmhy.org:104.25.27.31"

  u2magic-logs:
    image: python:3.13-alpine
    restart: unless-stopped
    depends_on:
      init:
        condition: service_completed_successfully
    command: ["python", "/app/log_server.py"]
    expose:
      - "18081"
    volumes:
      - ./u2magic/deploy/log_server.py:/app/log_server.py:ro
      - ./runtime/u2magic/logs:/app/logs:ro

  u2-scripts:
    build:
      context: ./u2_scripts
    image: u2-scripts-local:latest
    restart: unless-stopped
    depends_on:
      init:
        condition: service_completed_successfully
    environment:
      PYTHONUTF8: "1"
      U2_WEBUI_HOST: "0.0.0.0"
      U2_WEBUI_PORT: "18765"
      U2_WEBUI_CONFIG_PATH: "/runtime/webui_config.json"
      U2_WEBUI_LOG_DIR: "/runtime/logs"
      AUTO_MAGIC_DATA_PATH: "/runtime/auto_magic_seeds.data.txt"
      AUTO_MAGIC_LOG_PATH: "/runtime/auto_magic_seeds.log"
    expose:
      - "18765"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    volumes:
      - ./runtime/u2_scripts:/runtime

  gateway:
    build:
      context: ./nginx
    image: u2-gateway-local:latest
    restart: unless-stopped
    environment:
      NGINX_USERNAME: "admin"
      NGINX_PASSWORD: "请修改为自己的密码"
    depends_on:
      - u2magic
      - u2magic-logs
      - u2-scripts
    ports:
      - "18080:18080"
      - "18765:18765"
```

```bash
docker compose up -d --build
```

- U2Magic：`http://服务器IP:18080/`
- u2_scripts：`http://服务器IP:18765/`
