/* Shizu phone input. Formatting stays local; login submits the full international number. */
(() => {
  'use strict';

  const input = document.getElementById('phone_number');
  const library = window.libphonenumber;
  if (!input || !library) return;

  const countryBox = document.getElementById('phone_country');
  const countryName = document.getElementById('phone_country_name');
  const flag = document.getElementById('phone_flag');
  const callingCode = document.getElementById('phone_calling_code');
  const codes = new Set(library.getCountries().map(country => library.getCountryCallingCode(country)));
  let names;
  try {
    names = new Intl.DisplayNames([document.documentElement.lang || 'en'], {type: 'region'});
  } catch {
    // Country codes still identify the region in browsers without Intl.DisplayNames.
  }

  function displayCountry(formatter) {
    const country = formatter?.getCountry();
    const code = formatter?.getCallingCode();
    const caption = country
      ? names?.of(country) || country
      : code ? countryName.dataset[codes.has(code) ? 'shared' : 'international']
        : countryName.dataset.empty;
    if (countryName.textContent !== caption) countryName.textContent = caption;
    const symbol = country
      ? String.fromCodePoint(...Array.from(country, letter => 0x1f1e6 + letter.charCodeAt(0) - 65))
      : '🌐';
    if (flag.textContent !== symbol) flag.textContent = symbol;
    const prefix = code ? '+' + code : '';
    if (callingCode.textContent !== prefix) callingCode.textContent = prefix;
    if (country) countryBox.dataset.country = country;
    else delete countryBox.dataset.country;
  }

  function digits(value) {
    return (value.match(/[0-9]/g) || []).length;
  }

  function caretAt(value, count, originalPosition) {
    if (originalPosition === 0) return 0;
    if (count <= 0) return value.startsWith('+') ? 1 : 0;
    for (let index = 0, seen = 0; index < value.length; index++) {
      if (/[0-9]/.test(value[index]) && ++seen === count) return index + 1;
    }
    return value.length;
  }

  function format(value, start, end = start) {
    // Leave malformed input intact so login validation can explain the error.
    if (!/^[+0-9\s().\-\u2010-\u2015]*$/.test(value)) {
      displayCountry();
      return;
    }
    let number = value.replace(/[\s().\-\u2010-\u2015]/g, '');
    if (!/^\+?[0-9]*$/.test(number)) {
      displayCountry();
      return;
    }
    let removedDigits = 0;
    if (number.startsWith('00') && number.length > 2) {
      number = '+' + number.slice(2);
      removedDigits = 2;
    } else if (number && !number.startsWith('+') && !number.startsWith('0')) {
      number = '+' + number;
    }
    // Keep 0/00 while a user is still entering an international 00 prefix.
    const formatter = new library.AsYouType();
    const formatted = number.startsWith('0') ? number : formatter.input(number);
    displayCountry(formatter);
    if (input.value === formatted) return;
    const fromEnd = start === value.length;
    const toEnd = end === value.length;
    input.value = formatted;
    input.setSelectionRange(
      fromEnd ? formatted.length : caretAt(formatted, digits(value.slice(0, start)) - removedDigits, start),
      toEnd ? formatted.length : caretAt(formatted, digits(value.slice(0, end)) - removedDigits, end),
    );
  }

  input.addEventListener('input', event => {
    if (!event.isComposing) format(input.value, input.selectionStart, input.selectionEnd);
  });
  input.addEventListener('compositionend', () => format(input.value, input.selectionStart, input.selectionEnd));
  input.addEventListener('change', () => format(input.value, input.selectionStart, input.selectionEnd));
  input.addEventListener('beforeinput', event => {
    // Deleting an inserted separator should delete a digit, rather than reinsert
    // the separator forever. Selections and ordinary digit deletion use native editing.
    if (!event.cancelable || event.isComposing || input.selectionStart !== input.selectionEnd) return;
    const backward = event.inputType === 'deleteContentBackward';
    if (!backward && event.inputType !== 'deleteContentForward') return;
    const value = input.value;
    const cursor = input.selectionStart;
    let index = backward ? cursor - 1 : cursor;
    if (value[index] !== ' ') return;
    while (value[index] === ' ') index += backward ? -1 : 1;
    if (!/[0-9]/.test(value[index] || '')) return;
    event.preventDefault();
    const next = value.slice(0, index) + value.slice(index + 1);
    const position = backward ? index : cursor;
    input.value = next;
    format(next, position);
    // format() can leave an already formatted value unchanged.
    if (input.value === next) input.setSelectionRange(position, position);
  });

  format(input.value, input.selectionStart, input.selectionEnd);
})();
