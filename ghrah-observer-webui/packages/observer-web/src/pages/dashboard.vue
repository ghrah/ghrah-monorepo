<script setup lang="ts">
import ActionChainPanel from "@/components/action-chain/action-chain-panel.vue";
import AgentList from "@/components/agent-list.vue";
import ChatPanel from "@/components/chat/chat-panel.vue";
import HitlInbox from "@/components/hitl/hitl-inbox.vue";
import ProjectSelector from "@/components/nav/project-selector.vue";
import RoomSelector from "@/components/nav/room-selector.vue";
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="flex flex-1 min-h-0">
      <aside class="w-64 border-r border-gray-200 dark:border-gray-700 overflow-y-auto bg-white dark:bg-gray-900 flex flex-col">
        <ProjectSelector />
        <RoomSelector />
        <div class="flex-1 min-h-0 overflow-y-auto">
          <AgentList />
        </div>
      </aside>
      <section class="flex-1 flex flex-col min-w-0 bg-white dark:bg-gray-900">
        <ChatPanel />
      </section>
      <aside class="w-72 border-l border-gray-200 dark:border-gray-700 overflow-y-auto bg-white dark:bg-gray-900">
        <ActionChainPanel />
      </aside>
    </div>
    <footer class="border-t border-gray-200 dark:border-gray-700 max-h-52 overflow-y-auto bg-white dark:bg-gray-900">
      <HitlInbox />
    </footer>
  </div>
</template>
