import type { FormRules } from 'element-plus'

export const PASSWORD_MIN_LENGTH = 12
export const PASSWORD_MAX_LENGTH = 72

export function passwordConfirmationError(password: string, confirmation: string): string | null {
  return password === confirmation ? null : '两次输入的密码不一致'
}

export function buildResetPasswordRules(getPassword: () => string): FormRules {
  return {
    new_password: [
      { required: true, message: '请输入新密码', trigger: 'blur' },
      {
        min: PASSWORD_MIN_LENGTH,
        max: PASSWORD_MAX_LENGTH,
        message: `密码长度需为 ${PASSWORD_MIN_LENGTH}-${PASSWORD_MAX_LENGTH} 位`,
        trigger: 'blur',
      },
    ],
    confirm_password: [
      { required: true, message: '请再次输入新密码', trigger: 'blur' },
      {
        validator: (_rule: unknown, value: string, callback: (error?: string | Error) => void) => {
          const error = passwordConfirmationError(getPassword(), value)
          if (error) {
            callback(new Error(error))
          } else {
            callback()
          }
        },
        trigger: 'blur',
      },
    ],
  }
}
