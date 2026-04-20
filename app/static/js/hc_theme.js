/**
 * AmaldiStoria — Highcharts global theme
 * Caricato in base.html dopo highcharts.js quando presente.
 * Sovrascrive i default HC tramite setOptions() prima del render
 * di qualsiasi grafico — vince sugli stili inline SVG iniettati da HC.
 *
 * NON chiamare questo file se Highcharts non è caricato nella pagina:
 * viene incluso condizionalmente solo nei template che usano HC
 * tramite {% block scripts %}.
 */
(function () {
  if (typeof Highcharts === 'undefined') return;

  var FONT_SANS = 'Inter, system-ui, -apple-system, sans-serif';
  var FONT_HEAD = 'Cabin, ' + FONT_SANS;
  var C_INK     = '#101828';
  var C_INK2    = '#344054';
  var C_MUTED   = '#667085';

  Highcharts.setOptions({
    chart: {
      style: { fontFamily: FONT_SANS }
    },
    title: {
      style: {
        fontSize:   '13px',
        fontWeight: '600',
        color:      C_INK,
        fontFamily: FONT_HEAD
      }
    },
    subtitle: {
      style: {
        fontSize:   '11px',
        color:      C_MUTED,
        fontFamily: FONT_SANS
      }
    },
    legend: {
      itemStyle: {
        fontSize:   '11px',
        fontWeight: '500',
        color:      C_INK2,
        fontFamily: FONT_SANS
      }
    },
    tooltip: {
      style: {
        fontSize:   '12px',
        fontFamily: FONT_SANS
      }
    },
    xAxis: {
      labels: {
        style: {
          fontSize:   '11px',
          color:      C_MUTED,
          fontFamily: FONT_SANS
        }
      },
      title: {
        style: {
          fontSize:   '11px',
          color:      C_MUTED,
          fontFamily: FONT_SANS
        }
      }
    },
    yAxis: {
      labels: {
        style: {
          fontSize:   '11px',
          color:      C_MUTED,
          fontFamily: FONT_SANS
        }
      },
      title: {
        style: {
          fontSize:   '11px',
          color:      C_MUTED,
          fontFamily: FONT_SANS
        }
      }
    }
  });
}());
