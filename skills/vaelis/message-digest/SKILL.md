---
name: vaelis-message-digest
description: Extract hard deadlines and todos from WeChat/DingTalk/email digests into the North Star task queue. Use for butler message扫描 / DDL extraction.
version: 0.2.0
author: Vaelis
license: MIT
metadata:
  hermes:
    tags: [vaelis, butler, digest]
---

# Vaelis Message Digest

## Steps

1. Scan message sources (existing wechat-cli / dingtalk / Mind skills — reuse, don't rewrite).
2. For each hard DDL: `vaelis` `area=task` `action=enqueue` with risk `L0` or `L2` if a send is required.
3. `vaelis` `area=preview` `action=push` priority=progress.
4. `vaelis` `area=ops` `action=master_summarize` — never dump raw chats into Master.
