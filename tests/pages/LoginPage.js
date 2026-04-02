// Page Object Model para Login
class LoginPage {
  constructor(page) {
    this.page = page;
    this.usernameInput = '#id_username';
    this.passwordInput = '#id_password';
    this.submitButton = 'button[type="submit"]';
  }

  async goto() {
    await this.page.goto('/accounts/login');
  }

  async login(username, password) {
    await this.page.fill(this.usernameInput, username);
    await this.page.fill(this.passwordInput, password);
    await this.page.click(this.submitButton);
    await this.page.waitForLoadState('networkidle');
  }

  async loginAsAdmin() {
    await this.login('admin', 'admin');
  }

  async loginAsColaborador() {
    await this.login('colaborador', 'colaborador123');
  }

  async expectLoginError() {
    await this.page.waitForSelector('.bg-red-50');
  }
}

module.exports = { LoginPage };
