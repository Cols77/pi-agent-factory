import type { Component } from "@earendil-works/pi-tui";

export class ConfirmPrompt implements Component {
  private readonly title: string;
  private readonly message: string;
  private readonly onDecide: (confirmed: boolean) => void;

  constructor(title: string, message: string, onDecide: (confirmed: boolean) => void) {
    this.title = title;
    this.message = message;
    this.onDecide = onDecide;
  }

  // No cached render state -- required (non-optional) by pi-tui's Component
  // interface so this can be passed to tui.addChild()/tui.setFocus().
  invalidate(): void {}

  handleInput(data: string): void {
    if (data === "y" || data === "\r" || data === "\n") {
      this.onDecide(true);
    } else if (data === "n" || data === "\x1b") {
      this.onDecide(false);
    }
  }

  render(_width: number): string[] {
    return [this.title, "", this.message, "", "y confirm  n/Esc cancel"];
  }
}
