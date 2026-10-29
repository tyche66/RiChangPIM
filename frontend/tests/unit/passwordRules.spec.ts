import { describe, it, expect } from 'vitest'
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  buildResetPasswordRules,
  passwordConfirmationError,
} from '@/utils/passwordRules'

describe('passwordConfirmationError', () => {
  it('accepts identical passwords', () => {
    expect(passwordConfirmationError('ValidPassw0rd!', 'ValidPassw0rd!')).toBeNull()
  })

  it('rejects mismatched confirmation with a Chinese message', () => {
    expect(passwordConfirmationError('ValidPassw0rd!', 'DifferentPass1')).toBe('两次输入的密码不一致')
  })
})

describe('buildResetPasswordRules', () => {
  it('enforces the 8-72 length window on the new password', () => {
    const rules = buildResetPasswordRules(() => '') as any
    const lengthRule = rules.new_password.find((rule: any) => rule.min !== undefined)
    expect(lengthRule.min).toBe(PASSWORD_MIN_LENGTH)
    expect(lengthRule.max).toBe(PASSWORD_MAX_LENGTH)
    expect(lengthRule.message).toBe('密码长度需为 8-72 位')
  })

  it('validates confirmation against the current password', () => {
    let password = 'ValidPassw0rd!'
    const rules = buildResetPasswordRules(() => password) as any
    const confirmRule = rules.confirm_password.find((rule: any) => rule.validator)

    let error: Error | undefined
    confirmRule.validator({}, 'DifferentPass1', (value?: string | Error) => {
      error = value as Error
    })
    expect(error?.message).toBe('两次输入的密码不一致')

    error = undefined
    confirmRule.validator({}, 'ValidPassw0rd!', (value?: string | Error) => {
      error = value as Error
    })
    expect(error).toBeUndefined()

    password = 'OtherPassw0rd!'
    expect(passwordConfirmationError(password, 'ValidPassw0rd!')).toBe('两次输入的密码不一致')
  })
})
