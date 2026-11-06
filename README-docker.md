# 精简 Docker 镜像（GHCR）

当前只构建、测试并发布**一种普通 Docker 镜像**。不构建平台专用镜像，不安装云平台 CLI，也不在 GitHub Actions 中登录云账号或部署实例。

本方案按 **1 GiB 存储预算**精简，支持 `linux/amd64`。C++ 编译在 GitHub Actions 或 Docker 构建环境内完成，运行实例不需要安装编译器、Git 或构建工具。

## 1. 镜像与 GitHub Actions

本仓库当前镜像地址：

```text
ghcr.io/bitscr/subconverter-unikraft:latest
```

这是普通 Docker 镜像；仓库名中的 `unikraft` 不代表另一种镜像格式。当前不再生成 `:unikraft` 标签，使用 `:latest` 即可。

推送到 `master` / `main`，或手动运行 **Publish Slim Docker Image**：

1. 使用本仓库当前源码和 `Dockerfile.local` 构建，不重新克隆上游应用源码。
2. 检查镜像解压体积不超过 **200 MiB**，给 1 GiB 存储预算留出余量。
3. 测试只读根目录启动、内联与 HTTP 订阅转 Clash/sing-box、管理 Token 重载、端口覆盖与无效端口拒绝。
4. 将通过测试的 Docker 镜像推送到 GHCR。

`latest`、`sha-<完整提交 SHA>` 和版本标签指向同一种 Docker 镜像，不是不同的平台版本。默认分支生成 `latest`；`v*` 标签还会生成对应版本标签。

Fork 后镜像地址自动使用 `ghcr.io/<仓库所有者>/<仓库名的小写>`。

**Action 只使用 GitHub 自动提供的 `GITHUB_TOKEN`。** 不需要配置 Docker Hub 密码、云平台账号或云平台 Token。CI 中的 `API_TOKEN=ci-smoke-token` 仅用于功能测试，不会写入发布的镜像。

首次发布后，到 GitHub **Packages → 包设置 → Change visibility → Public**，让部署环境可以匿名拉取。

## 2. Docker 启动：1 CPU / 4 GiB 内存

将 `YOUR_RANDOM_LONG_TOKEN` 换成自己的随机管理密码，再执行：

```sh
docker pull ghcr.io/bitscr/subconverter-unikraft:latest
docker run -d --name subconverter --restart unless-stopped --read-only --tmpfs /tmp:rw,nosuid,size=64m --memory 4g --cpus 1 -e API_TOKEN=YOUR_RANDOM_LONG_TOKEN -p 25500:25500 ghcr.io/bitscr/subconverter-unikraft:latest
```

检查服务：

```sh
curl http://127.0.0.1:25500/version
```

正常返回 `subconverter v... backend`。这是转换后端，没有前端首页；根路径 `/` 返回 404 不代表启动失败。

你也可以只使用上面的镜像地址，在自己的部署工具中设置：

| 参数 | 值 |
| --- | --- |
| 镜像 | `ghcr.io/bitscr/subconverter-unikraft:latest` |
| CPU / 内存 | `1` / `4 GiB` |
| 容器目标端口 | `25500` |
| 环境变量 | `API_TOKEN=自己的随机管理密码` |
| 额外持久卷 | 默认不需要 |

部署工具的镜像导入和公网端口配置由你自行管理，Action 不参与云端部署。

## 3. 端口

程序默认监听 `0.0.0.0:25500`。

- Docker 的 `-p 主机端口:容器端口` 决定端口映射。
- 例如 `-p 8080:25500` 表示访问主机的 8080，容器内部仍为 25500。
- 如果要改容器内部端口，设置 `PORT=8080`，映射也改为 `-p 8080:8080`。
- `PORT` 在启动时读取，修改后需要重新创建容器。
- Dockerfile 的 `EXPOSE 25500` 只是声明，不能代替实际端口映射。

配置中的 7890、2080 等是导出给客户端的代理端口，不是这个转换后端需要开放的端口。

## 4. API_TOKEN

`API_TOKEN` 是管理接口密码，不是 GitHub Token，也不是云平台登录 Token。当前入口要求设置它，未设置会启动失败。

可以用 Python 生成一个 64 字符的安全随机密码：

```sh
python -c "import secrets; print(secrets.token_hex(32))"
```

将生成的值用于运行环境变量，不要提交到 GitHub。

**它保护管理接口，不是 `/sub` 的访问密码。** 普通转换接口仍公开；不要公开包含私人订阅凭证的转换链接。如果需要仅本人访问，请在部署环境中另加访问控制。

## 5. 精简内容与持久配置

- 多阶段构建，运行层只带程序、动态库、HTTPS CA 证书和约 3 MiB 的原有配置资源。
- 程序使用 `-Os` 并去除调试符号，保留原有格式转换和 JavaScript 支持。
- 不运行 `scripts/update_rules.py`，不额外下载大型默认规则库。
- 默认规则只保留 `GEOIP,CN,DIRECT` 和其余流量走 `PROXY`，保留 `PROXY` / `AUTO` 两个组。
- 关闭磁盘缓存和静态文件服务；工作线程为 2，单次下载上限 16 MiB。
- 运行配置与临时文件位于 `/tmp/subconverter`。上面的 Docker 示例将 `/tmp` 放在内存中，不挂载额外持久卷。

运行时修改不作为持久配置保存，重新创建容器会丢失。长期修改请编辑仓库中的 `unikraft/pref.ini` 后重新构建；这个目录沿用原有路径，文件仍用于唯一的 Docker 镜像。

订阅转换结果通过 HTTP 返回给客户端，不需要保存在服务器的持久卷中。镜像自身仍占用存储，实际占用以部署环境显示为准。

## 6. 使用与本地构建

转换接口：

```text
http://<主机>:25500/sub?target=clash&url=<经过 URL 编码的订阅链接>
http://<主机>:25500/sub?target=singbox&url=<经过 URL 编码的订阅链接>
```

需要完整分流时仍可传 `&config=<经过 URL 编码的远程配置链接>`。精简的是默认规则和部署内容，不是转换格式。

在有 Docker 的构建电脑上自行构建：

```sh
docker build -f Dockerfile.local -t subconverter:slim .
```

不要在只有 1 GiB 存储的运行环境中进行编译。CI 的 Docker 冒烟测试不代表已经验证所有部署环境；实际部署后仍需检查 `/version`，并用自己的订阅做一次转换。
