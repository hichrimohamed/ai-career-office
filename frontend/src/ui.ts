/** Small DOM helpers shared by the board panels. */

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, className = '', text = ''): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

export function button(label: string, onClick: () => void, className = 'card-button'): HTMLButtonElement {
  const node = el('button', className, label);
  node.type = 'button';
  node.addEventListener('click', onClick);
  return node;
}

/** A Copy button that flashes "Copied" and reports failures through `onError`. */
export function copyButton(
  getText: () => string,
  onError: (message: string) => void,
  label = 'Copy',
  className = 'card-button primary',
): HTMLButtonElement {
  const node = button(label, async () => {
    try {
      await navigator.clipboard.writeText(getText());
      node.textContent = 'Copied';
      setTimeout(() => (node.textContent = label), 1500);
    } catch {
      onError('Copy failed. Select the text and copy it by hand.');
    }
  }, className);
  return node;
}
