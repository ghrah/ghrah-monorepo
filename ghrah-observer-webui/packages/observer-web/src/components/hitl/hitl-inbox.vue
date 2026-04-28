<script setup lang="ts">
import { useHitlStore } from "@ghrah/observer-core";
import HitlRequestItem from "./hitl-request-item.vue";

const hitl = useHitlStore();

function handleApprove(promiseId: string) {
  hitl.removeRequest(promiseId);
}

function handleReject(promiseId: string) {
  hitl.removeRequest(promiseId);
}
</script>

<template>
  <div class="hitl-inbox">
    <h3>HITL Inbox</h3>
    <ul v-if="hitl.pendingRequests.length > 0">
      <HitlRequestItem
        v-for="req in hitl.pendingRequests"
        :key="req.promiseId"
        :request="req"
        @approve="handleApprove"
        @reject="handleReject"
      />
    </ul>
    <p v-else class="empty">No pending requests</p>
  </div>
</template>

<style scoped>
.hitl-inbox {
  padding: 0.5rem;
}

.hitl-inbox h3 {
  margin: 0 0 0.5rem;
}

.hitl-inbox ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.empty {
  color: #999;
  font-size: 0.875rem;
}
</style>
