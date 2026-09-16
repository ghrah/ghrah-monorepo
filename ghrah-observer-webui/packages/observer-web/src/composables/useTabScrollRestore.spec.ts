// @vitest-environment happy-dom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { type ComponentPublicInstance, defineComponent, h, nextTick, ref } from "vue";
import type { ScrollRestoreTarget, TabScrollRestoreOptions } from "./useTabScrollRestore";
import { useTabScrollRestore } from "./useTabScrollRestore";

// happy-dom 无真实布局（scrollHeight/clientHeight 恒 0），按元素属性模拟可滚动容器，
// scrollTop 赋值带钳制语义（模拟浏览器对越界赋值的收敛）。
function mockScrollable(el: HTMLElement, scrollHeight: number, clientHeight: number): void {
  let top = 0;
  Object.defineProperty(el, "scrollHeight", { configurable: true, get: () => scrollHeight });
  Object.defineProperty(el, "clientHeight", { configurable: true, get: () => clientHeight });
  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    get: () => top,
    set: (v: number) => {
      top = Math.max(0, Math.min(v, scrollHeight - clientHeight));
    },
  });
}

interface PaneOptions {
  contentKey?: TabScrollRestoreOptions["contentKey"];
  target?: () => ScrollRestoreTarget;
}

// 面板宿主：KeepAlive 内 v-if 切换停用/激活，捕获真实滚动元素供断言
function mountKeepAlivePane(options: PaneOptions = {}) {
  let el: HTMLElement | null = null;
  const Pane = defineComponent({
    setup() {
      const container = ref<HTMLElement | null>(null);
      const restore = useTabScrollRestore(container, {
        contentKey: options.contentKey,
        target: options.target,
      });
      return () =>
        h("div", {
          ref: (node: Element | ComponentPublicInstance | null) => {
            container.value = (node as HTMLElement | null) ?? null;
            el = container.value;
          },
          onScroll: restore.onScroll,
        });
    },
  });
  const show = ref(true);
  const Host = defineComponent({
    components: { Pane },
    setup() {
      return { show };
    },
    template: `<div><KeepAlive><Pane v-if="show" /><div v-else>other</div></KeepAlive></div>`,
  });
  const wrapper = mount(Host);
  return {
    wrapper,
    el: () => el,
    async hide() {
      show.value = false;
      await nextTick();
    },
    async showPane() {
      show.value = true;
      await nextTick();
      await nextTick();
    },
  };
}

describe("useTabScrollRestore", () => {
  it("停用→激活后恢复用户滚动位置", async () => {
    const host = mountKeepAlivePane();
    const el = host.el();
    if (!el) throw new Error("scroll container missing");
    mockScrollable(el, 1000, 200);

    el.scrollTop = 500;
    el.dispatchEvent(new Event("scroll"));
    expect(el.scrollTop).toBe(500);

    await host.hide();
    el.scrollTop = 0; // 模拟浏览器在 DOM 脱离文档时重置 scrollTop
    await host.showPane();
    expect(el.scrollTop).toBe(500);
    host.wrapper.unmount();
  });

  it("target 返回 bottom 时激活即落底", async () => {
    const host = mountKeepAlivePane({ target: () => "bottom" });
    await host.hide();
    const el = host.el();
    if (!el) throw new Error("scroll container missing");
    mockScrollable(el, 1000, 200);
    el.scrollTop = 0;

    await host.showPane();
    expect(el.scrollTop).toBe(800); // 1000 - 200
    host.wrapper.unmount();
  });

  it("内容收缩被钳制时挂起重试，contentKey 增长后补恢复", async () => {
    const contentLength = ref(50);
    const host = mountKeepAlivePane({ contentKey: () => contentLength.value });
    const el = host.el();
    if (!el) throw new Error("scroll container missing");
    mockScrollable(el, 1000, 200);

    el.scrollTop = 500;
    el.dispatchEvent(new Event("scroll"));
    await host.hide();
    mockScrollable(el, 100, 200); // 模拟内容收缩（如 LRU 逐出后重挂）
    el.scrollTop = 0;
    await host.showPane();
    expect(el.scrollTop).toBe(0); // 钳制：max = 100 - 200 < 0

    mockScrollable(el, 1000, 200); // 内容补拉到位
    contentLength.value = 100;
    await nextTick();
    await nextTick();
    expect(el.scrollTop).toBe(500);
    host.wrapper.unmount();
  });

  it("用户滚动接管后不再重放旧目标", async () => {
    const contentLength = ref(50);
    const host = mountKeepAlivePane({ contentKey: () => contentLength.value });
    const el = host.el();
    if (!el) throw new Error("scroll container missing");
    mockScrollable(el, 1000, 200);

    el.scrollTop = 500;
    el.dispatchEvent(new Event("scroll"));
    await host.hide();
    mockScrollable(el, 100, 200);
    await host.showPane();
    expect(el.scrollTop).toBe(0); // 钳制恢复失败，挂起重试

    mockScrollable(el, 1000, 200); // 内容补齐（scrollTop 归零）
    el.scrollTop = 30; // 用户接管滚动
    el.dispatchEvent(new Event("scroll"));
    contentLength.value = 100;
    await nextTick();
    await nextTick();
    expect(el.scrollTop).toBe(30); // 保持用户位置而非重放 500
    host.wrapper.unmount();
  });
});
