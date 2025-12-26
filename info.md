{% if installed %}

## Changes as compared to your installed version:

### Breaking Changes

  {% if version_installed.replace("v", "").replace(".","") | int < 20 %}
- Configuration flow now requires a valid Amber API token to proceed.
  {% endif %}

### Changes

### Features

  {% if version_installed.replace("v", "").replace(".","") | int < 10  %}
- Initial Amber Balance sensor that calculates your monthly position from usage and feed-in data.
- Automatic site discovery during configuration.
  {% endif %}
  {% if version_installed.replace("v", "").replace(".","") | int < 20  %}
- HACS-ready packaging and updated documentation.
  {% endif %}

### Bugfixes

  {% if version_installed.replace("v", "").replace(".","") | int < 20  %}
- Improved handling of authentication/site discovery errors in the config flow.
  {% endif %}

---

{% else %}

## Track your Amber Balance

Calculate your current monthly position using Amber usage/export data, daily surcharge, and subscription costs. Configure via the UI; automatic site discovery included.
{% endif %}
