### 一、U2 功能
一键对接 U2 官方站点 + 专属魔法接口，自动获取站点种子、流量优惠等核心信息
### 二、qBittorrent 下载器全功能管理
-   #### 全局规则统一配置
自定义上传速度限速、下载器最大并发任务数
种子添加速度阈值（超过限速自动禁止添加）
-  #### 多节点集群管理
支持配置多个 qBittorrent 下载节点，实现负载分发
单节点可独立覆盖全局配置（限速、任务数、速度限制），灵活管控
- #### 智能节点调度（核心特色）
按种子大小区分大种子 / 小种子，动态分配权重
大种子优先保障存储空间，小种子优先保障上传速度，自动选择最优下载节点
### 三、无人值守自动刷种（上车）
支持一键开启 / 关闭自动刷种核心功能
自定义定时任务（当前配置每分钟执行一次），实现 7×24 小时无人值守自动运行
### 四、种子智能精准过滤
严格筛选优质种子，杜绝无效做种，支持 4 类过滤规则：
流量优惠过滤：仅添加指定上传 / 下载倍率种子（当前配置：免费下载种 + 1 倍上传）
大小过滤：限定种子大小范围（如: 最小 1GB ~ 最大 600GB）
做种人数过滤：可配置超过 x 人做种的热门种子自动跳过
用户过滤：忽略指定用户（自身）发布的种子，避免重复做种



## 1. 步骤 1：创建宿主机挂载目录
（直接复制执行）：

运行

```plain
mkdir -p /data/docker/u2/config && \
mkdir -p /data/docker/u2/logs && \
mkdir -p /data/docker/u2/data
```

目录用途：

- /data/docker/u2/config ：存放核心配置文件
- /data/docker/u2/logs ：存放程序运行日志
- /data/docker/u2/logs ：存放程序数据文件

---

## 2. 步骤 2：编写核心配置文件
/data/docker/u2/config/application-base.yml

### 2.1 创建并编辑配置文件
执行命令：

```plain
vim /data/docker/u2/config/application-base.yml
```

```
khc:
  # ====== 1. U2 站点认证配置【必填修改】 ====
  site:
    # 魔法接口域名（无需修改）
    #kysdDomain: ''
    # 站点域名（无需修改）
    #webDomain: ''
    # 站点登录Cookie【替换为你的U2 Cookie】
    cookie: U2网站cookie
    # 站点密钥【替换为你的U2 Passkey】
    passkey: 替换为你的U2 Passkey
    # 用户ID【替换为你的U2数字UID】
    uid: U2的用户id, 数字
    # V1模式API令牌【替换为你的U2 APIToken】
    apitoken: 令牌

  # ============ 2. qbittorrent配置【必填修改】 ============
  qbittorrent:
    # 下载器全局限制配置
    global:
      # 上传限速, 单位byte 50MB/s = 48*1024*1024
      upload-limit: 180*1024*1024
      # 下载器最大任务数
      max-torrent-size-limit: 12
      # 下载器最大速度限制
      max-torrent-speed-limit: 300*1024*1024
      # 种子分类名称
      category: U2
      # 是否先首尾下载
      firstLastPiecePrio: true
    # QbNode选择权重配置（无需修改）
    qbNodeWeight:
      # 大种子标准, 大于此值为大种子
      seedSizeThreshold: 50* 1024 * 1024 * 1024
      largeSeedSpaceWeight: 0.8
      largeSeedSpeedWeight: 0.2
      smallSeedSpaceWeight: 0.3
      smallSeedSpeedWeight: 0.7
    # 下载器节点配置【替换为你的QB节点信息】
    nodes:
      - name: qb-node1
        host: http://ip:端口
        username: 账号
        password: 密码
      # 以下配置项, 配置了以下面的为准, 优先于全局
      #  upload-limit: 180*1024*1024
      #  max-torrent-size-limit: 12
      #  max-torrent-speed-limit: 300*1024*1024
      - name: qb-node2
        host: http://ip:端口
        username: 账号
        password: 密码

  # ===================== 4. 定时任务配置 =====================
  schedule:
    # 是否启用自动上车
    enable: true
    # 每分钟执行一次（无需修改）
    cron: 0 * * * * ?

  # ===================== 5. 业务过滤配置 =====================
  business:
    # 上传倍率大于等于指定倍率, 如2.0 , 只要2x倍以上上传的种子，才允许添加
    upRate: 1.0
    # 载倍率小于等于指定倍率, 如0.5 , 只要0.5x倍及以下的种子，才允许添加
    downRate: 0.0
    # 种子大小最小限制 单位：byte, 为0或空则不限制
    torrentMinSize: 1 * 1024 * 1024 * 1024
    # 种子大小最小限制 单位：byte, 为0或空则不限制
    torrentMaxSize: 600 * 1024 * 1024 * 1024
    # 做种人数，大于此人数的种子，刚不添加, 为空或不配置则不限制
    seeders: 20

  # 接口签名token【自定义设置，用于手动上车】
  web:
    sign-token: 你的签名token
```





>    v1模式apitoken获取方式：
>
>           1、油猴安装 https://greasyfork.org/zh-CN/scripts/428545脚本
>
>           2、打开https://u2域名/forums.php?action=viewtopic&topicid=13495&page=p150133#pid150133
>
>           3、点击按钮自动获取apitoken
>

### 2.2 保存配置文件
 → 回车保存退出

---

## 3. 步骤 3：启动 Docker 容器
### 3.1 直接复制执行启动命令
运行

```plain
docker run -d \
  --name u2magic \
  -p 18080:18080 \
  -v /data/docker/u2/config/application-base.yml:/data/u2Magic/config/application-base.yml \
  -v /data/docker/u2/logs:/data/u2Magic/logs \
  -v /data/docker/u2/data:/data/u2 \
  --add-host=填写u2网店域名:104.25.27.31  \
  kuanghom/u2magic:latest
```




---

## 4. 步骤 4：验证容器运行状态
1. 查看容器是否运行：

运行

```plain
docker ps
```

 ✅ 看到 u2magic 容器状态为 即启动成功


查看运行日志（排查问题用）：

运行

```plain
docker logs -f u2magic
```

---

## 5. 功能使用：手动上车接口
### 5.1 接口地址
plaintext

```plain
手动上车接口
http://服务器IP:18080/addTorrent.html?token=你的签名token
手动初始化token接口
http://服务器IP:18080/token.html
配置管理
http://服务器IP:18080/index.html?token=你的签名token

ps: 手动初始token, 会把token缓存到浏览器中, 请求其他接口, 就不需要带?token的方式访问了
```

### 8.2 替换说明
1. 服务器IP ：你的服务器公网 IP
2. 18080：容器映射的端口（默认不变）
3. 签名token ：配置⽂件中 web.sign-token 的值



---

## 6. 核心配置参数详解
### 6.1 U2 站点认证（必须修改）
- cookie：U2 网站登录 Cookie
- passkey：U2 个人密钥
- uid：U2 用户数字 ID
- apitoken：U2 接口令牌

### 6.2 qBittorrent 节点
- host：QB 访问地址（http://IP: 端口）
- username/password：QB 登录账号密码

### 6.3 业务过滤
- upRate：上传倍率限制
- downRate：下载倍率限制
- torrentMinSize/MaxSize：种子大小限制

### 6.4 接口令牌

- sign-token：手动上车接口的验证密钥

---

## 7. 常用容器管理命令
运行

```plain
# 停止容器
docker stop u2magic

# 启动容器
docker start u2magic

# 重启容器
docker restart u2magic

# 删除容器（需先停止）
docker rm u2magic

# 查看实时日志
docker logs -f u2magic
```

---

## 8. 常见问题排查
### 8.1 容器启动失败
1. 检查配置文件格式（YAML 严格缩进，不能用 Tab）
2. 检查挂载目录是否创建成功
3. 检查 18080 端口是否被占用

### 8.2 无法访问手动上车接口
1. 服务器安全组 / 防火墙开放 18080 端口
2. 确认容器正常运行（docker ps ）
3. 核对 token 是否和配置文件一致

### 8.3 无法添加种子到 QB
1. 检查 QB 节点地址、账号密码是否正确
2. 检查服务器能否访问 QB 端口
3. 查看容器日志定位错误
