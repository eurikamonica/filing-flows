# 站长操作清单：把 Filing Flows 搬到自己的服务器

这份清单只列**需要你亲自做**的事，按顺序做，一次一步。每一步都写了它的作用。
技术细节在 [README.md](README.md)（英文），你不需要看。

- 服务器：OVHcloud VPS，地址 `135.148.205.18`，用户名 `ubuntu`
- 网站：GitHub 继续每 15 分钟扫描、生成网站；变化的只是"网站放在哪里"
- 所有网址不变；在你确认之前，正式网站一直由 GitHub Pages 提供，不受影响
- **改域名解析、关闭 GitHub Pages、删除任何东西之前，都会先问你**

"终端"是指：Mac 上的「终端」(Terminal) 应用；Windows 上的「PowerShell」。
在终端里输入命令后按回车。输入密码时屏幕上不显示任何字符，这是正常的。

---

## 第一阶段：你自己的登录钥匙（以后登录服务器不用密码）

**第 1 步　在你的电脑上生成钥匙**
在终端输入 `ssh-keygen -t ed25519`，然后连按 3 次回车（全部用默认）。
作用：在你电脑上生成一对钥匙。私钥留在你电脑里，公钥等下放到服务器上。
如果提示已经存在（`already exists`），说明以前生成过，输入 `n` 回车即可，直接用原来的。

**第 2 步　把公钥放到服务器上（最后一次用密码）**
- Mac：`ssh-copy-id ubuntu@135.148.205.18`
- Windows：
  `type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh ubuntu@135.148.205.18 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"`

第一次连接会问 `Are you sure you want to continue connecting`，输入 `yes` 回车；然后输入密码管理器里的服务器密码。
作用：服务器从此认得你的电脑。

**第 3 步　试一下不用密码登录**
`ssh ubuntu@135.148.205.18`　→ 不再问密码就直接进去了，就成功了。看到 `ubuntu@...$` 提示符说明已在服务器里。

## 第二阶段：一键安装

**第 4 步　在服务器里运行安装命令**（登录状态下）
`curl -fsSL https://raw.githubusercontent.com/eurikamonica/filing-flows/main/deploy/server/setup.sh | sudo bash`
大约 2–5 分钟，最后显示「✔ 安装完成」。如果中途问密码，输入服务器密码。
作用：安装网站服务器软件 Caddy、防火墙（只开 22/80/443）、自动安全更新、日志上限，并建好专门给 GitHub 用的上传账号。
这一步不会影响现在的网站。

## 第三阶段：让 GitHub 能把网站传上来

**第 5 步　显示要交给 GitHub 的 3 个机密**
`sudo ff-deploy-key show`
屏幕会显示 3 段内容，分别在 `=== DEPLOY_SSH_KEY ===`、`=== DEPLOY_KNOWN_HOSTS ===`、`=== DEPLOY_HOST ===` 下面。
作用：这是一把只能"上传网站"的专用钥匙，别的什么都做不了。

**第 6 步　在 GitHub 添加这 3 个机密**（每个都做一遍）
GitHub 仓库页面 → **Settings** → 左侧 **Secrets and variables** → **Actions** → **New repository secret**
- Name 填 `DEPLOY_SSH_KEY`，Secret 粘贴第一段（从 `-----BEGIN` 那行到 `-----END` 那行，整段）→ **Add secret**
- Name 填 `DEPLOY_KNOWN_HOSTS`，Secret 粘贴第二段 → **Add secret**
- Name 填 `DEPLOY_HOST`，Secret 填 `135.148.205.18` → **Add secret**

作用：GitHub 每次生成网站后，会用这把钥匙把变化的文件传到服务器。添加后，下一次扫描（15 分钟内）就会第一次完整上传。

**第 7 步　看一眼服务器上的网站**
浏览器打开 `http://135.148.205.18/`，能看到网站就成功了（这个预览地址不会被搜索引擎收录）。

**第 8 步　删掉服务器上那份私钥**
`sudo ff-deploy-key forget`
作用：私钥已经保存在 GitHub，服务器上不需要再留一份。

## 第四阶段：关闭密码登录

**第 9 步　只允许钥匙登录**
`sudo ff-ssh-lockdown`
然后**先别关这个窗口**，另开一个新终端，输入 `ssh ubuntu@135.148.205.18`，能进去就成功了，再关掉旧窗口。
作用：从此别人就算猜到密码也登不进服务器。万一进不去，在旧窗口输入 `sudo ff-ssh-lockdown --undo` 撤回。

## 第五阶段：新旧对比测试

**第 10 步　运行对比**（我也可以替你运行）
GitHub 仓库 → **Actions** → 左侧 **Site monitor** → **Run workflow** → 勾选 **compare** → **Run workflow**。
作用：抽查约 300 个页面和所有关键规则，对比现在的网站和新服务器：状态码、跳转、内容是否一致。我会看结果告诉你。

## 第六阶段：正式切换（每一步我都会先问你）

**第 11 步　决定是否开 Cloudflare 代理（橙色云朵）**
我会说明利弊，你来决定。我的建议是开：切换和回退都只要几秒、证书提前装好不会出错、亚洲和欧洲读者更快。

**第 12 步　记下现在的 DNS 记录**
Cloudflare → 你的域名 → **DNS** → **Records**，把 `filing-flows.com` 和 `www` 的所有记录截图保存。
作用：万一需要回到 GitHub Pages，照着截图改回去即可。

**第 13 步（开代理时）　装 Cloudflare 证书**
Cloudflare → **SSL/TLS** → **Origin Server** → **Create Certificate** → 保持默认 → **Create**。
在服务器运行 `sudo ff-site origin --paste`，按提示先粘贴证书、再粘贴私钥。
然后 **SSL/TLS** → **Overview** → 选 **Full (strict)**；**Caching** → **Configuration** → **Browser Cache TTL** 选 **Respect Existing Headers**。

**第 13 步（不开代理时）　调低 TTL**
提前一天把这两条记录的 TTL 改成 **1 min**。切换当天在服务器运行 `sudo ff-site live --wait-dns`，让它等着。

**第 14 步　修改 DNS 记录**（我会根据你的截图告诉你具体改哪几条）
把 `filing-flows.com` 和 `www` 指向 `135.148.205.18`，并删掉指向 GitHub 的旧记录。
作用：从这一刻起，访客看到的是新服务器。

**第 15 步　观察几天**
GitHub Pages 继续保留几天作为后备（两边都会收到每次更新）。我会检查 Search Console 抓取是否正常。

**第 16 步　关闭 GitHub Pages**（确认稳定后，我会先问你）
GitHub 仓库 → **Settings** → **Pages** → 关闭；然后 **Settings** → **Secrets and variables** → **Actions** → **Variables** 标签 → **New repository variable**，Name 填 `PAGES_DEPLOY`，Value 填 `off`。

---

## 以后

- **每日报告**：开头会多一句服务器状态（硬盘用了多少、最后更新时间、有没有问题）。
- **网站监控**：每半小时自动检查一次；出问题会发邮件给你，恢复后再发一封。
- **出问题时**：服务器坏了也不会丢东西——网站每 15 分钟由 GitHub 重新生成。可以把 DNS 改回第 12 步的截图（GitHub Pages 还开着时），或者换一台新服务器。
- **换服务商**：新服务器上重做第 1–9 步，然后把 DNS 指向新地址。证书（第 13 步）可以原样再用。
