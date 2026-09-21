# ghrah-taskstore

ghrah 任务归因内核（L3，零 ghrah 域包依赖）：tasks / claims / evidence 三表 sqlite 权威、命令/查询 facade、确定性转移（边界 impure / 转移 pure）与 checker 扩展点宿主。

依赖链：`ghrah-plugin` ← `ghrah-taskstore` ← `ghrah-subject`（无环）。wire 映射归 ghrah-subject 的 TaskStoreUnit，本包不感知协议。