# Homebrew formula for Gmail CLI

class GmailCli < Formula
  desc "Command-line interface for Gmail"
  homepage "https://github.com/nitaiaharoni/gmail-cli"
  url "https://github.com/nitaiaharoni/gmail-cli/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "" # Update with actual SHA256 after release
  license "MIT"
  head "https://github.com/nitaiaharoni/gmail-cli.git", branch: "main"

  depends_on "python@3.11"

  def install
    python3 = "python3.11"
    system python3, "-m", "pip", "install", "--prefix=#{prefix}", "."
  end

  def post_install
    # Ensure credentials directory exists
    system "mkdir", "-p", "#{ENV["HOME"]}/.gmail"
  end

  test do
    system "#{bin}/gmail", "--version"
  end

  def caveats
    <<~EOS
      Gmail CLI has been installed!

      To get started:
      1. Download credentials.json from Google Cloud Console:
         - Go to https://console.cloud.google.com/
         - Create/select a project
         - Enable Gmail API
         - Create OAuth 2.0 credentials (Desktop app)
         - Download as credentials.json
         - Place it in the current directory or ~/

      2. Run setup:
         gmail init

      3. Then use: gmail help
    EOS
  end
end

