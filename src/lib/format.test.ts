import { describe, expect, it } from 'vitest';
import { formatarReais, formatarValor } from './format';
import { linkWhatsApp } from './whatsapp';

describe('formatação de valores', () => {
  it('usa vírgula decimal e duas casas', () => {
    expect(formatarValor(79.99)).toBe('79,99');
    expect(formatarValor(109)).toBe('109,00');
    expect(formatarReais(189.99)).toBe('R$ 189,99');
  });
});

describe('linkWhatsApp', () => {
  it('abre a conversa com o número comercial', () => {
    expect(linkWhatsApp()).toBe('https://wa.me/552120423744');
  });

  it('inclui a mensagem codificada quando informada', () => {
    expect(linkWhatsApp('Olá! Quero o plano')).toBe(
      'https://wa.me/552120423744?text=Ol%C3%A1!%20Quero%20o%20plano',
    );
  });
});
