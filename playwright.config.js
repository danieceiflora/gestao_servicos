const { defineConfig, devices } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/e2e',
  
  // Timeout por teste
  timeout: 30000,
  
  // Retry em caso de falha (flaky tests)
  retries: process.env.CI ? 2 : 0,
  
  // Workers (testes paralelos)
  workers: process.env.CI ? 1 : 2,
  
  // Reporter
  reporter: [
    ['html', { outputFolder: 'tests/playwright-report' }],
    ['list'],
  ],
  
  use: {
    // URL base
    baseURL: 'http://localhost:8000',
    
    // Screenshots apenas em falhas
    screenshot: 'only-on-failure',
    
    // Vídeo apenas em falhas
    video: 'retain-on-failure',
    
    // Trace para debug
    trace: 'on-first-retry',
    
    // Timeout de navegação
    navigationTimeout: 15000,
  },

  // Projetos (browsers)
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Descomente para testar em mais browsers
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'mobile',
    //   use: { ...devices['Pixel 5'] },
    // },
  ],

  // Iniciar servidor automaticamente
  webServer: {
    command: 'python manage.py runserver',
    url: 'http://localhost:8000',
    timeout: 120000,
    reuseExistingServer: !process.env.CI,
  },
});
