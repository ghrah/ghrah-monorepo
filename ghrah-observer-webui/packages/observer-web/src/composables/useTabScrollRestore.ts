import { nextTick, onActivated, type Ref, type WatchSource, watch } from "vue";

/** 滚动恢复目标：number 为绝对 scrollTop；"bottom" 落底；null 恢复上次记录的用户滚动位置。 */
export type ScrollRestoreTarget = number | "bottom" | null;

export interface TabScrollRestoreOptions {
  /** 内容规模信号（如条目数）；变化后在下一 tick 重放恢复目标，覆盖补拉/钳制后内容异步到达的场景。 */
  contentKey?: WatchSource<unknown>;
  /** 激活与内容变化时的恢复目标；缺省恢复记录位置。 */
  target?: () => ScrollRestoreTarget;
}

/**
 * 标签面板滚动位置缓存（配合 KeepAlive 使用）。滚动事件里持续记录位置——
 * KeepAlive 停用时 DOM 脱离文档、scrollTop 会被浏览器重置，无法依赖停用时机读取；
 * 激活或内容变化时重放恢复目标。
 */
export function useTabScrollRestore(
  container: Ref<HTMLElement | null | undefined>,
  options: TabScrollRestoreOptions = {},
): { onScroll: () => void; applyScroll: () => void } {
  let savedTop = 0;
  // 最近一次程序式赋值的生效值：scroll 事件与之吻合视为回声，不算用户滚动
  let programmedTop: number | null = null;

  function maxScrollTop(el: HTMLElement): number {
    return Math.max(0, el.scrollHeight - el.clientHeight);
  }

  /** 重放恢复目标；内容未渲染或被钳制时静默跳过，待 contentKey 变化再重放。 */
  function applyScroll(): void {
    const el = container.value;
    if (!el) return;
    const target = options.target?.() ?? null;
    const desired = target === "bottom" ? maxScrollTop(el) : (target ?? savedTop);
    if (Math.abs(el.scrollTop - desired) <= 1) return;
    el.scrollTop = desired;
    programmedTop = el.scrollTop;
  }

  /** 记录用户滚动位置；须由模板 `@scroll.passive` 绑定。 */
  function onScroll(): void {
    const el = container.value;
    if (!el) return;
    if (programmedTop !== null && Math.abs(el.scrollTop - programmedTop) <= 1) return;
    programmedTop = null;
    savedTop = el.scrollTop;
  }

  onActivated(() => {
    void nextTick(applyScroll);
  });

  if (options.contentKey) {
    watch(options.contentKey, () => {
      void nextTick(applyScroll);
    });
  }

  return { onScroll, applyScroll };
}
