# Unikraft 1 GiB 精简部署

本方案按你确认的 **1 GiB 磁盘/存储限制**设计。编译只发生在 GitHub Actions，部署实例不安装编译器、Git 或 Docker 构建工具。

## 本次精简了什么

- 只构建 Unikraft 公共平台使用的 `linux/amd64`。
- 多阶段构建，运行镜像只带程序、动态库、HTTPS CA 证书和约 3 MiB 的原有配置资源。
- 不运行 `scripts/update_rules.py`，不在构建时克隆、下载额外的大型规则库。
- 程序使用 `-Os` 编译并去除调试符号；保留原有格式转换、模板和 JavaScript 支持。
- 默认分流只保留 `GEOIP,CN,DIRECT` 和其余流量走 `PROXY`；保留 `PROXY`、`AUTO` 两个组。不是原版完整广告/媒体分流。
- 关闭磁盘缓存和静态文件服务，工作线程为 2；单次下载上限 16 MiB。
- 运行配置在 `/tmp/subconverter`，不需要额外持久卷。运行时改动不是持久配置，重新创建实例会丢失；长期修改请编辑 `unikraft/pref.ini` 后重新构建。
- Actions 会检查普通 Docker 镜像的**解压层合计不超过 200 MiB**，给 1 GiB 限制留出空间。Unikraft 还会添加兼容运行时，最终占用以平台显示为准，不把源码大小当成镜像大小。

## 1. Push 后如何构建

推送到 `master` 或 `main`，或手动运行 **Publish Slim Docker and Unikraft Images**：

1. 构建的是**本仓库当前提交**，不会重新克隆上游 subconverter。
2. 检查体积，运行 Docker 冒烟测试。
3. 使用 `GITHUB_TOKEN` 推送到 `ghcr.io/<仓库所有者>/<仓库名的小写>`。
4. 仅在主分支推送时，把已经测试的 Docker 镜像打包成 `base-compat` + EROFS 的 Unikraft 镜像；不会第二次编译 C++。

以本仓库当前 remote 为例：

| 镜像 | 用途 |
| --- | --- |
| `ghcr.io/bitscr/subconverter-unikraft:latest` | 普通 Docker 镜像，本地 Docker 测试用 |
| `ghcr.io/bitscr/subconverter-unikraft:sha-<完整提交 SHA>` | 本次提交的 Docker 镜像，CI 用它打包 |
| `ghcr.io/bitscr/subconverter-unikraft:unikraft` | 部署到 Unikraft，优先使用这个 |

Fork 到其他账户时，Action 会自动采用新仓库名称。第一次发布后，到 GitHub **Packages → 包设置 → Change visibility → Public**，让平台能匿名拉取；不要把 GitHub 写入令牌放进运行镜像。

不需要 `DOCKER_USERNAME`、`DOCKER_PASSWORD` 或 Unikraft 账户令牌来发布 GHCR 镜像。创建云实例时才需要 `unikraft login`。原来的跨平台二进制构建改为手动触发，避免每次 push 再跑多套无关构建。

## 2. 端口到底由谁决定

**不是网站随机发给你一个端口，也不是写了 Docker `EXPOSE` 就自动开放。**

| 层次 | 本方案设置 | 含义 |
| --- | --- | --- |
| 程序监听地址 | `0.0.0.0` | 允许平台网关访问实例 |
| 程序内部端口 | `25500` | `unikraft/pref.ini` 默认值；可用 `PORT` 环境变量覆盖 |
| 外部端口 | `443` | HTTPS 标准端口 |
| 服务映射 | `443:25500/http+tls` | 网关终止 TLS，再把 HTTP 发到程序的 25500 |
| 可选外部端口 | `80:443/http+redirect` | HTTP 重定向到 HTTPS |

平台分配的是公网 **FQDN 域名**。用默认 HTTPS 端口时，访问 `https://<平台分配的域名>/version`，**不用加 `:25500`**。

官方服务规则：

- 外部 `443` 必须有 `http` 和 `tls` handler。
- 外部 `80` 必须有 `http`，不能有 `tls`；可用 `redirect` 跳到 443。
- 其他外部端口只能使用 `tls`，不能使用 `http` handler。因此这个 HTTP API 推荐统一用 443。
- Dockerfile 的 `EXPOSE` 在 Unikraft 中被忽略，必须创建上述服务映射。

内部端口可以改成 8080 等有效 TCP 端口，但映射的目标端口必须同步修改。例如设置 `PORT=8080` 时使用 `443:8080/http+tls`。`PORT` 只在程序启动时读取，修改后需要重启。

这里的 25500 是**转换后端服务端口**；配置中的 7890、2080 等是导出给客户端的代理端口，不需要在这个服务器上开放。

## 3. 推荐部署命令

安装[官方 Unikraft CLI](https://unikraft.com/docs/cli/overview)，登录后执行。下面是一行命令，PowerShell 和 Bash 均可用：

```sh
unikraft login
unikraft run --metro sin --name subconverter --image ghcr.io/bitscr/subconverter-unikraft:unikraft --memory 512MiB --vcpus 1 --publish 443:25500/http+tls --publish 80:443/http+redirect --env API_TOKEN=YOUR_RANDOM_LONG_TOKEN
```

- `sin` 只是示例，请换成你的账户实际可用的 metro。
- 先分配 **1 vCPU / 512 MiB 内存**即可，不必一次用完 4 GiB；真实订阅特别大时可调高内存。
- `YOUR_RANDOM_LONG_TOKEN` 必须换成自己的随机长字符串。入口要求提供 `API_TOKEN`，避免使用原版固定的 `password`。
- 此处使用兼容运行时，不要求启用需要额外套餐权限的 full Linux VM。
- 创建服务后，命令输出的 `service.domains[].fqdn` 是访问域名。

修改内部端口的示例：

```sh
unikraft run --metro sin --name subconverter --image ghcr.io/bitscr/subconverter-unikraft:unikraft --memory 512MiB --vcpus 1 --publish 443:8080/http+tls --env PORT=8080 --env API_TOKEN=YOUR_RANDOM_LONG_TOKEN
```

如果通过控制台创建实例/服务，填写同样的参数，字段名称以当前界面为准：

| 参数 | 值 |
| --- | --- |
| Unikraft 镜像 | `ghcr.io/bitscr/subconverter-unikraft:unikraft` |
| vCPU / 内存 | `1` / `512 MiB` |
| 内部目标端口 | `25500` |
| 外部服务端口 | `443` |
| handler / 协议 | `http` + `tls` |
| 环境变量 | `API_TOKEN=自己的随机长字符串` |

## 4. 验证和使用

先访问：

```text
https://<平台分配的域名>/version
```

正常返回 `subconverter v... backend`。本项目是后端，没有前端首页；根路径 `/` 返回 404 不等于程序没启动。

转换接口保持不变：

```text
https://<平台分配的域名>/sub?target=clash&url=<经过 URL 编码的订阅链接>
https://<平台分配的域名>/sub?target=singbox&url=<经过 URL 编码的订阅链接>
```

需要完整分流时仍可传 `&config=<经过 URL 编码的远程配置链接>`。精简的是默认规则和部署内容，不是订阅格式转换代码。

**`API_TOKEN` 保护管理接口，并不是 `/sub` 的访问密码。** 默认 `/sub` 仍能被公开调用；不要把含私人订阅凭证的转换链接发到公开场合。需要仅本人访问时，应另加访问控制，不把目前的 token 机制误认为全站鉴权。

## 5. 本地 Docker 和手动打包

这两项在有 Docker 的构建电脑上执行，**不要在那台 1 GiB 的部署实例上编译**。

普通 Docker 测试：

```sh
docker run --rm --read-only --tmpfs /tmp:rw,nosuid,size=64m -e API_TOKEN=YOUR_RANDOM_LONG_TOKEN -p 127.0.0.1:25500:25500 ghcr.io/bitscr/subconverter-unikraft:latest
```

访问 `http://127.0.0.1:25500/version`。本地要自行编译时：

```sh
docker build -f Dockerfile.local -t subconverter:slim .
```

如需手动重新打包到 Unikraft，`unikraft/Dockerfile` 只从已有的小镜像复制根文件系统：

```sh
unikraft build ./unikraft --build-arg IMAGE=ghcr.io/bitscr/subconverter-unikraft:latest --output ghcr.io/bitscr/subconverter-unikraft:unikraft
```

推送 GHCR 前需要先用 Docker 登录该仓库。正常情况下 Action 已经完成此步骤，无需重复手动打包。

## 检查范围

Action 包含：完整 C++ 编译、普通 Docker 镜像体积检查、只读根目录启动、内联及 HTTP 订阅转 Clash/sing-box、管理 token 重载、自定义 `PORT=8080`、无效端口拒绝，以及 Unikraft EROFS 打包。

Docker 冒烟测试不等于已在 Unikraft 实机上测试。首次部署后仍需检查 `/version` 并用自己的真实订阅做一次转换；这里不会宣称已经验证你账户的网络可达性。

## 官方文档依据

- [Services：端口映射、handler 和域名](https://unikraft.com/docs/platform/services)
- [Docker 应用迁移：兼容运行时与启动命令](https://unikraft.com/docs/tutorials/docker-to-ukc)
- [Rootfs formats：EROFS、CPIO、RAM overlay](https://unikraft.com/docs/tutorials/rootfs-formats)
- [CLI run](https://unikraft.com/docs/cli/unikraft/run)
- [CLI build](https://unikraft.com/docs/cli/unikraft/build)
