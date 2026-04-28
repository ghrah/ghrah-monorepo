<script setup lang="ts">
import ActionChainPanel from "@/components/action-chain/action-chain-panel.vue";
import AgentList from "@/components/agent-list.vue";
import ChatPanel from "@/components/chat/chat-panel.vue";
import HitlInbox from "@/components/hitl/hitl-inbox.vue";
</script>

<template>
  <div class="dashboard">
    <div class="dashboard-main">
      <aside class="dashboard-sidebar">
        <AgentList />
      </aside>
      <section class="dashboard-chat">
        <ChatPanel />
      </section>
      <aside class="dashboard-chain">
        <ActionChainPanel />
      </aside>
    </div>
    <footer class="dashboard-hitl">
      <HitlInbox />
    </footer>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.dashboard-main {
  display: flex;
  flex: 1;
  min-height: 0;
}

.dashboard-sidebar {
  width: 220px;
  border-right: 1px solid #ddd;
  overflow-y: auto;
}

.dashboard-chat {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.dashboard-chain {
  width: 300px;
  border-left: 1px solid #ddd;
  overflow-y: auto;
}

.dashboard-hitl {
  border-top: 1px solid #ddd;
  max-height: 200px;
  overflow-y: auto;
}
</style>
