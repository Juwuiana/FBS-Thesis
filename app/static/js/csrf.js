(function () {
  const unsafeMethods = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

  function getToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }

  function isSameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch {
      return false;
    }
  }

  const nativeFetch = window.fetch;
  window.fetch = function (input, init) {
    const requestInput = typeof Request !== 'undefined' && input instanceof Request;
    const method = String((init && init.method) || (requestInput && input.method) || 'GET').toUpperCase();
    const url = requestInput ? input.url : input;
    const token = getToken();

    if (!unsafeMethods.has(method) || !token || !isSameOrigin(url)) {
      return nativeFetch.apply(this, arguments);
    }

    const headers = new Headers(
      (init && init.headers) || (requestInput ? input.headers : undefined)
    );
    if (!headers.has('X-CSRFToken')) {
      headers.set('X-CSRFToken', token);
    }

    return nativeFetch.call(this, input, Object.assign({}, init, { headers }));
  };

  const xhrState = new WeakMap();
  const xhrPrototype = XMLHttpRequest.prototype;
  const nativeOpen = xhrPrototype.open;
  const nativeSend = xhrPrototype.send;
  const nativeSetRequestHeader = xhrPrototype.setRequestHeader;

  xhrPrototype.open = function (method, url) {
    const result = nativeOpen.apply(this, arguments);
    xhrState.set(this, { method: String(method).toUpperCase(), url, csrfHeaderSet: false });
    return result;
  };

  xhrPrototype.setRequestHeader = function (name, value) {
    const result = nativeSetRequestHeader.apply(this, arguments);
    if (String(name).toLowerCase() === 'x-csrftoken') {
      const state = xhrState.get(this);
      if (state) state.csrfHeaderSet = true;
    }
    return result;
  };

  xhrPrototype.send = function () {
    const state = xhrState.get(this);
    const token = getToken();
    if (
      state &&
      unsafeMethods.has(state.method) &&
      token &&
      isSameOrigin(state.url) &&
      !state.csrfHeaderSet
    ) {
      this.setRequestHeader('X-CSRFToken', token);
    }
    return nativeSend.apply(this, arguments);
  };
})();
