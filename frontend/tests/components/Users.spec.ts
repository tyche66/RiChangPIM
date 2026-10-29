import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => {
  const userApi = {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    resetPassword: vi.fn(),
  }
  const roleApi = { list: vi.fn() }
  return { default: {}, userApi, roleApi }
})

const errorSpy = vi.spyOn(ElMessage, 'error').mockImplementation(() => {})
const successSpy = vi.spyOn(ElMessage, 'success').mockImplementation(() => {})

import { roleApi, userApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import Users from '@/views/Users.vue'

const mockList = userApi.list as any
const mockCreate = userApi.create as any
const mockReset = userApi.resetPassword as any
const mockRoles = roleApi.list as any

const ElDialogStub = {
  props: {
    modelValue: { type: Boolean, default: false },
    title: { type: String, default: '' },
  },
  template: '<div v-if="modelValue" class="dialog-stub"><slot /><slot name="footer" /></div>',
}

const ElFormStub = {
  methods: {
    validate(callback: (valid: boolean) => void) {
      callback(true)
    },
    resetFields() {},
    clearValidate() {},
  },
  template: '<form><slot /></form>',
}

function mountUsers(roleCode: string, stubs: Record<string, unknown> = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useAuthStore()
  store.roleCode = roleCode
  store.permissions = ['user:view', 'user:create', 'user:edit', 'user:delete']

  return mount(Users, {
    global: {
      plugins: [pinia, ElementPlus],
      stubs: { 'el-dialog': ElDialogStub, ...stubs },
    },
  })
}

function findButton(wrapper: ReturnType<typeof mountUsers>, text: string) {
  return wrapper.findAll('button').find((button) => button.text() === text)
}

describe('Users.vue', () => {
  beforeEach(() => {
    mockList.mockReset()
    mockCreate.mockReset()
    mockReset.mockReset()
    mockRoles.mockReset()
    errorSpy.mockClear()
    successSpy.mockClear()

    mockList.mockResolvedValue({
      data: {
        list: [
          {
            id: 'u-1',
            username: 'alice',
            email: '',
            phone: '',
            role_id: 'r-1',
            status: 'active',
            last_login_time: null,
            create_time: '2026-10-29T00:00:00Z',
          },
        ],
        total: 1,
      },
    })
    mockRoles.mockResolvedValue({ data: { list: [{ id: 'r-1', role_name: '管理员' }] } })
  })

  it('shows the reset-password button only for system admins', async () => {
    const admin = mountUsers('admin')
    await flushPromises()
    expect(admin.text()).toContain('重设密码')

    const sales = mountUsers('sales')
    await flushPromises()
    expect(sales.text()).not.toContain('重设密码')
  })

  it('shows exactly one toast with the backend message when create fails', async () => {
    mockCreate.mockRejectedValue({
      response: {
        status: 409,
        data: { detail: { code: 40901, msg: '用户名已被占用（含已删除用户），请更换用户名' } },
      },
    })

    const wrapper = mountUsers('admin', { 'el-form': ElFormStub })
    await flushPromises()

    await findButton(wrapper, '新增用户')!.trigger('click')
    const dialog = wrapper.find('.dialog-stub')
    const inputs = dialog.findAll('input')
    await inputs[0].setValue('alice')
    await inputs[1].setValue('Passw0rd!')

    await findButton(wrapper, '确定')!.trigger('click')
    await flushPromises()

    expect(mockCreate).toHaveBeenCalledTimes(1)
    expect(mockCreate.mock.calls[0][1]).toEqual({ suppressErrorMessage: true })
    expect(errorSpy).toHaveBeenCalledTimes(1)
    expect(errorSpy).toHaveBeenCalledWith('用户名已被占用（含已删除用户），请更换用户名')
    expect(errorSpy).not.toHaveBeenCalledWith('创建失败')
  })

  it('submits the new password after confirmation and shows one success toast', async () => {
    mockReset.mockResolvedValue({ code: 200, msg: '密码已重设，该用户需重新登录' })

    const wrapper = mountUsers('admin', { 'el-form': ElFormStub })
    await flushPromises()

    await findButton(wrapper, '重设密码')!.trigger('click')
    const dialog = wrapper.find('.dialog-stub')
    const passwords = dialog.findAll('input[type="password"]')
    expect(passwords).toHaveLength(2)
    await passwords[0].setValue('ValidPassw0rd!')
    await passwords[1].setValue('ValidPassw0rd!')

    await findButton(wrapper, '确定')!.trigger('click')
    await flushPromises()

    expect(mockReset).toHaveBeenCalledWith(
      'u-1',
      { new_password: 'ValidPassw0rd!' },
      { suppressErrorMessage: true }
    )
    expect(successSpy).toHaveBeenCalledTimes(1)
  })

  it('shows exactly one toast when reset password fails', async () => {
    mockReset.mockRejectedValue({
      response: { status: 403, data: { detail: { code: 40301, msg: '仅系统管理员可重设用户密码' } } },
    })

    const wrapper = mountUsers('admin', { 'el-form': ElFormStub })
    await flushPromises()

    await findButton(wrapper, '重设密码')!.trigger('click')
    const passwords = wrapper.find('.dialog-stub').findAll('input[type="password"]')
    await passwords[0].setValue('ValidPassw0rd!')
    await passwords[1].setValue('ValidPassw0rd!')
    await findButton(wrapper, '确定')!.trigger('click')
    await flushPromises()

    expect(errorSpy).toHaveBeenCalledTimes(1)
    expect(errorSpy).toHaveBeenCalledWith('仅系统管理员可重设用户密码')
  })
})
