# Resend 邮件订阅配置指南

## 1. 注册 Resend 账号

1. 访问 https://resend.com/
2. 使用 GitHub 账号登录
3. 免费版每月可发送 3,000 封邮件（足够个人使用）

## 2. 获取 API Key

1. 登录 Resend Dashboard
2. 点击左侧 "API Keys"
3. 点击 "Create API Key"
4. 命名为 `travel-ai-dashboard`
5. 复制生成的 API Key（格式：`re_xxxxxxxxxxxxx`）

## 3. 配置 GitHub Secrets

1. 打开 https://github.com/bozi93/travel-ai-dashboard/settings/secrets/actions
2. 点击 "New repository secret"
3. 添加以下两个 secrets：

| Name | Value |
|------|-------|
| `RESEND_API_KEY` | 刚才复制的 Resend API Key |
| `FROM_EMAIL` | `Travel AI Dashboard <onboarding@resend.dev>` |

> 注意：免费版默认使用 `onboarding@resend.dev` 作为发件人。如需自定义域名，请在 Resend Dashboard 添加并验证域名。

## 4. 添加订阅者

编辑 `subscribers.json` 文件，添加邮箱地址：

```json
{
  "subscribers": [
    "your-email@example.com",
    "another-email@example.com"
  ]
}
```

## 5. 测试

1. 在 GitHub Actions 页面手动触发 "Run workflow"
2. 检查是否收到邮件通知
3. 查看 Actions 日志确认发送状态

## 6. 自动触发

配置完成后，每天北京时间 16:00 GitHub Actions 会自动：
1. 抓取 RSS 和 Reddit 数据
2. 发现新公司并更新 data.json
3. 如果有新公司，发送邮件给所有订阅者

## 可选：自定义发件域名

1. 在 Resend Dashboard 添加域名
2. 按照 DNS 验证指引配置你的域名
3. 验证成功后，将 `FROM_EMAIL` secret 改为 `noreply@yourdomain.com`
