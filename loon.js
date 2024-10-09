const GEOSITE_URL = 'https://raw.githubusercontent.com/rdone4425/meta-rules-dat/meta/geo/geosite/cn.list';
const GEOIP_URL = 'https://raw.githubusercontent.com/rdone4425/meta-rules-dat/meta/geo/geoip/cn.list';

let geositeData = null;
let geoipData = null;

// 加载 GeoSite 和 GeoIP 数据
async function loadGeoData() {
  try {
    const geositeResponse = await $httpClient.get(GEOSITE_URL);
    const geoipResponse = await $httpClient.get(GEOIP_URL);

    if (geositeResponse.status === 200 && geoipResponse.status === 200) {
      geositeData = geositeResponse.body.split('\n').filter(line => line.trim() !== '');
      geoipData = geoipResponse.body.split('\n').filter(line => line.trim() !== '');
      console.log('成功加载 GeoSite 和 GeoIP 数据');
    } else {
      throw new Error('加载地理数据失败');
    }
  } catch (error) {
    console.error('加载地理数据失败:', error);
  }
}

// 检查域名是否匹配 GeoSite 规则
function matchGeoSite(domain) {
  return geositeData.some(rule => {
    if (rule.startsWith('+.')) {
      return domain.endsWith(rule.slice(2));
    } else {
      return domain === rule;
    }
  });
}

// 检查 IP 是否匹配 GeoIP 规则
function isChineseIP(ip) {
  return geoipData.some(cidr => {
    const [network, mask] = cidr.split('/');
    const ipLong = ip2long(ip);
    const networkLong = ip2long(network);
    const maskLong = (0xffffffff << (32 - parseInt(mask))) >>> 0;
    return (ipLong & maskLong) === (networkLong & maskLong);
  });
}

// IP 地址转换为长整型
function ip2long(ip) {
  return ip.split('.').reduce((long, octet) => (long << 8) + parseInt(octet), 0) >>> 0;
}

// 主函数
async function main(params) {
  if (!geositeData || !geoipData) {
    await loadGeoData();
  }

  const domain = params.domain;
  if (!domain) {
    $done({ error: 'Missing domain parameter' });
    return;
  }

  try {
    const dnsResult = await $dns.lookup(domain);
    const ip = dnsResult.address;
    const isChineseIPAddress = isChineseIP(ip);
    const isChinaDomain = matchGeoSite(domain);

    let outbound = (isChineseIPAddress || isChinaDomain) ? 'DIRECT' : 'PROXY';

    $done({
      response: {
        status: 200,
        body: JSON.stringify({
          domain: domain,
          ip: ip,
          isChineseIP: isChineseIPAddress,
          isChinaDomain: isChinaDomain,
          outbound: outbound
        })
      }
    });
  } catch (error) {
    $done({ error: `DNS lookup failed: ${error}` });
  }
}

// 脚本入口
$done({ script_name: "域名路由", script_author: "Assistant", script_function: main });