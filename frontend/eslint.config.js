import globals from 'globals'
import js from '@eslint/js'
import hooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'

export default tseslint.config({ ignores: ['dist','tests'] }, js.configs.recommended, ...tseslint.configs.recommended, { files: ['src/**/*.{ts,tsx}'], languageOptions: { globals: globals.browser }, plugins: { 'react-hooks': hooks }, rules: { ...hooks.configs.recommended.rules } })
