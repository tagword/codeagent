// 诊断：直接测试页面切换
(function debugTeamHub() {
  function _debug(phase, data) {
    try { console.log('[DEBUG]', phase, JSON.stringify(data)); } catch(_) {}
  }

  // 监控 body 属性变化
  var _body = document.body;
  var _origSetAttr = _body.setAttribute.bind(_body);
  _body.setAttribute = function(name, value) {
    _debug('setAttribute', {name: name, value: value});
    return _origSetAttr(name, value);
  };

  // 拦截 switchToPage
  var _origSwitch = window.switchToPage;
  if (typeof _origSwitch === 'function') {
    window.switchToPage = function(id) {
      _debug('switchToPage called', {id: id});
      var target = document.getElementById('page-' + id);
      if (target) {
        _debug('target element', {
          id: target.id,
          display: getComputedStyle(target).display,
          hasActive: target.classList.contains('active'),
          inlineStyle: target.getAttribute('style')
        });
      } else {
        _debug('target NOT FOUND', {id: 'page-' + id});
      }
      return _origSwitch(id);
    };
  }

  // 手动测试函数
  window._debugShowTeam = function() {
    _debug('_debugShowTeam called', {});
    var body = document.body;
    body.setAttribute('data-activity-mode', 'team');
    var p = document.getElementById('page-team');
    if (p) {
      p.classList.add('active');
      p.style.removeProperty('display');
      _debug('after show', {
        display: getComputedStyle(p).display,
        hasActive: p.classList.contains('active'),
        attr: body.getAttribute('data-activity-mode')
      });
    } else {
      _debug('page-team element NOT FOUND in DOM', {});
    }
  };

  window._debugShowHub = function() {
    _debug('_debugShowHub called', {});
    var body = document.body;
    body.setAttribute('data-activity-mode', 'hub');
    var p = document.getElementById('page-hub');
    if (p) {
      p.classList.add('active');
      p.style.removeProperty('display');
      _debug('after show', {
        display: getComputedStyle(p).display,
        hasActive: p.classList.contains('active'),
        attr: body.getAttribute('data-activity-mode')
      });
    } else {
      _debug('page-hub element NOT FOUND in DOM', {});
    }
  };

  _debug('debug script loaded', {
    teamExists: !!document.getElementById('page-team'),
    hubExists: !!document.getElementById('page-hub'),
    switchToPageExists: typeof window.switchToPage === 'function',
    switchActivityModeExists: typeof window.switchActivityMode === 'function',
    workspaceExists: !!document.querySelector('.workspace'),
  });
})();
