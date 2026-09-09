<script setup lang="ts">
defineProps<{ label?: string }>();
</script>

<template>
  <ul class="sidebar-list" :aria-label="label"><slot /></ul>
</template>
