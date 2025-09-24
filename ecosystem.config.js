module.exports = {
  apps: [
    {
      name: 'reflex-api',
      script: '/home/ubuntu/.local/bin/uv',
      args: 'run python main.py',
      cwd: '/home/ubuntu/reflex/api',
      env: {
        NODE_ENV: 'production'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      error_file: './logs/api-err.log',
      out_file: './logs/api-out.log',
      log_file: './logs/api-combined.log',
      time: true
    },
    {
      name: 'reflex-web',
      script: 'npm',
      args: 'start',
      cwd: '/home/ubuntu/reflex/web',
      env: {
        NODE_ENV: 'production',
        PORT: '3000',
        NEXT_PUBLIC_API_BASE_URL: 'http://18.188.37.30:8000'
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      error_file: './logs/web-err.log',
      out_file: './logs/web-out.log',
      log_file: './logs/web-combined.log',
      time: true
    }
  ]
}