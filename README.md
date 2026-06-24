# U2Magic + u2_scripts Docker Compose

使用一个 Docker Compose 同时运行：

- U2Magic
- `u2_scripts` Auto Magic Seeds WebUI
- U2Magic 日志服务
- Nginx 统一登录网关

两个应用自身的 WebUI 密码已经关闭，外部只能通过 Nginx 暴露的统一账号密码访问。

## 使用前修改密码

编辑 `docker-compose.yml`：

```yaml
gateway:
  environment:
    NGINX_USERNAME: "admin"
    NGINX_PASSWORD: "change-me-now"
```

请务必将默认密码改成自己的强密码。

## 启动

```bash
docker compose up -d --build
docker compose ps
```

首次启动时，`init` 服务会从 `config-templates/` 复制空白配置到本机 `runtime/`。`runtime/` 已被 Git 忽略，不会上传 Cookie、Token、qB 密码、日志和数据库。

访问地址：

- U2Magic：`http://服务器IP:18080/`
- u2_scripts：`http://服务器IP:18765/`

U2Magic 的默认接口 Token 是：

```text
change-me-token
```

首次登录后，请分别在两个 WebUI 中填写自己的 U2 Cookie、API Token、UID 和 qBittorrent 节点信息，并修改 U2Magic 的接口 Token。

修改 U2Magic 接口 Token 时，需要同步修改：

- `config-templates/u2magic/application-base.yml`
- U2Magic WebUI 中的 `signToken`

## 常用命令

```bash
docker compose logs -f
docker compose restart
docker compose down
```

修改统一登录密码后，重新创建网关：

```bash
docker compose up -d --build --force-recreate gateway
```

需要恢复全新的空白配置时：

```bash
docker compose down
rm -rf runtime
docker compose up -d --build
```

Windows PowerShell 删除运行配置：

```powershell
docker compose down
Remove-Item -Recurse -Force runtime
docker compose up -d --build
```

## 安全说明

- 不要提交 `runtime/`。
- 不要将真实 Cookie、Passkey、API Token 或 qB 密码写进 `config-templates/`。
- 默认提供的是 HTTP Basic Auth；公网使用时建议再配置 HTTPS、Cloudflare Tunnel 或其他 TLS 入口。
- `u2magic` 和 `u2-scripts` 只使用 Docker 内部端口，只有 Nginx 网关发布宿主机端口。

## 上游项目

- [Kuanghom/U2Magic](https://github.com/Kuanghom/U2Magic)
- [Haruite/u2_scripts](https://github.com/Haruite/u2_scripts)
