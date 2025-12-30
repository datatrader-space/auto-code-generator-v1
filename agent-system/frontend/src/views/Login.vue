<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
    <div class="max-w-md w-full">
      <!-- Card -->
      <div class="bg-white rounded-lg shadow-xl p-8">
        <!-- Logo/Title -->
        <div class="text-center mb-8">
          <h1 class="text-3xl font-bold text-gray-900 mb-2">Auto Code Generator</h1>
          <p class="text-gray-600">{{ isLogin ? 'Sign in to your account' : 'Create your account' }}</p>
        </div>

        <!-- Error Message -->
        <div v-if="error" class="mb-4 bg-red-50 border border-red-200 rounded-lg p-4">
          <p class="text-red-800 text-sm">{{ error }}</p>
        </div>

        <!-- Success Message -->
        <div v-if="success" class="mb-4 bg-green-50 border border-green-200 rounded-lg p-4">
          <p class="text-green-800 text-sm">{{ success }}</p>
        </div>

        <!-- Form -->
        <form @submit.prevent="handleSubmit">
          <!-- Email/Username -->
          <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">
              {{ isLogin ? 'Email or Username' : 'Email' }}
            </label>
            <input
              v-model="formData.username"
              type="text"
              required
              class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              :placeholder="isLogin ? 'Enter your email or username' : 'Enter your email'"
            />
          </div>

          <!-- Password -->
          <div class="mb-6">
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Password
            </label>
            <input
              v-model="formData.password"
              type="password"
              required
              class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="Enter your password"
            />
          </div>

          <!-- Submit Button -->
          <button
            type="submit"
            :disabled="loading"
            class="w-full bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition"
          >
            {{ loading ? 'Please wait...' : (isLogin ? 'Sign In' : 'Sign Up') }}
          </button>
        </form>

        <!-- Toggle Login/Register -->
        <div class="mt-6 text-center">
          <button
            @click="toggleMode"
            type="button"
            class="text-blue-600 hover:text-blue-700 text-sm"
          >
            {{ isLogin ? "Don't have an account? Sign up" : 'Already have an account? Sign in' }}
          </button>
        </div>

        <!-- GitHub OAuth -->
        <div class="mt-8">
          <div class="relative">
            <div class="absolute inset-0 flex items-center">
              <div class="w-full border-t border-gray-300"></div>
            </div>
            <div class="relative flex justify-center text-sm">
              <span class="px-2 bg-white text-gray-500">After logging in</span>
            </div>
          </div>

          <div class="mt-6">
            <p class="text-sm text-gray-600 text-center">
              You can connect your GitHub account to browse repositories
            </p>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <p class="text-center text-gray-600 text-sm mt-8">
        Auto Code Generator v1.0
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../services/api'

const router = useRouter()

const isLogin = ref(true)
const loading = ref(false)
const error = ref(null)
const success = ref(null)

const formData = ref({
  username: '',
  password: ''
})

const toggleMode = () => {
  isLogin.value = !isLogin.value
  error.value = null
  success.value = null
  formData.value = { username: '', password: '' }
}

const handleSubmit = async () => {
  try {
    loading.value = true
    error.value = null
    success.value = null

    const data = {
      username: formData.value.username,
      password: formData.value.password,
      email: formData.value.username // Use username as email for simplicity
    }

    if (isLogin.value) {
      // Login
      const response = await api.login(data)

      if (response.data.success) {
        success.value = 'Login successful! Redirecting...'

        // Store user data and redirect
        localStorage.setItem('user', JSON.stringify(response.data.user))

        setTimeout(() => {
          router.push('/')
        }, 500)
      }
    } else {
      // Register
      const response = await api.register(data)

      if (response.data.success) {
        success.value = 'Account created successfully! Redirecting...'

        // Store user data and redirect
        localStorage.setItem('user', JSON.stringify(response.data.user))

        setTimeout(() => {
          router.push('/')
        }, 500)
      }
    }
  } catch (err) {
    console.error('Auth error:', err)
    error.value = err.response?.data?.error || 'An error occurred. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>
