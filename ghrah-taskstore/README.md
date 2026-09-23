# ghrah-taskstore

ghrah 任务归因内核（L3，零 ghrah 域包依赖）：tasks / claims / evidence 三表 sqlite 权威、命令/查询 facade、确定性转移（边界 impure / 转移 pure）与 checker 扩展点宿主。

**定位**：**可选组件**（非系统必要组件）——没有它系统仍能完成大部分工作，它只做加强；它是**首个接入插件系统的插件**，目标装配形态是插件（经 `ghrah.plugins` 发现 + 信任闸 + Project 装配清单挂载）。当前由 `ghrah-subject` 经 builtin 链挂载，属**待纠正偏离**；`GHRAH_SUBJECT_TASKSTORE_ENABLED=false` 时不挂载。

依赖链：`ghrah-plugin` ← `ghrah-taskstore` ← `ghrah-subject`（无环）。wire 映射归 ghrah-subject 的 TaskStoreUnit，本包不感知协议。