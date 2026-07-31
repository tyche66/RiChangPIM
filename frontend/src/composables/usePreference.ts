/**
 * 浏览器端的用户习惯持久化。
 *
 * 存的只是「界面偏好」——视图模式、列宽策略、每页条数这类用户随时能自己改回来
 * 的东西。不存业务数据，也不存敏感信息：例如产品列表成本价的「眼睛」开关就故意
 * 不持久化，否则下次打开页面会直接把成本价摊在屏幕上。
 *
 * 约定：
 * - 键统一加 `pim:pref:` 前缀，和令牌（token / refresh_token）这类运行时状态分开，
 *   清理偏好时范围一眼可见。
 * - localStorage 是用户可改的，取到不认识的值就退回默认值，不让脏数据卡住界面。
 * - 底层用 @vueuse/core 的 useStorage，自带序列化和多标签页同步。
 */
import { useStorage } from '@vueuse/core'

const PREFIX = 'pim:pref:'

/**
 * 读写一条界面偏好。
 *
 * @param key 偏好名，建议用 `模块.字段`，例如 `products.viewMode`
 * @param fallback 默认值，同时决定序列化方式
 * @param allowed 可选的白名单；存量值不在白名单内时回落到默认值
 */
export function usePreference<T>(key: string, fallback: T, allowed?: readonly T[]) {
  const state = useStorage<T>(`${PREFIX}${key}`, fallback)
  if (allowed && !allowed.includes(state.value)) state.value = fallback
  return state
}
