# torrent_info

libtorrent를 이용해 마그넷이나 토렌트 파일의 정보를 보여주는 SJVA 플러그인

## 요구조건

libtorrent가 설치가능한 모든 환경.

자동 설치는 아래 환경만 지원합니다.
- x86_64
- alpine 3.10
- docker

네이티브라면 직접 설치 후 설정 페이지에서 설치 여부를 확인할 수 있습니다.

## 준비과정

## 더 읽어보기

## Changelog

v0.0.1.1 - libtorrent-1.2.4-200211.tar.gz

v0.0.1.0
- SJVA0.2: 웹 연동 대응

v0.0.0.9
- LOGIC: 코드 정리, 소소한 수정
- WEBUI: magnet uri text-truncate

v0.0.0.8
- LOGIC: 캐시 임시 수정

v0.0.0.7 - libtorrent-1.2.3-191227.tar.gz
- alpine3.10
- python2.7.17
- libboost1.71
- libtorrent1.2.3

v0.0.0.6
- WEBUI: 마그넷 + 토렌트 파일 하나로 통합
- LOGIC: 사용자 트래커 기능
- LOGIC: 시간 데이터 로컬 기준으로 통일

v0.0.0.5
- WEBUI: 결과를 json 대신 좀 더 보기 좋은 포맷으로
- WEBUI: 항목 클릭해서 복사
- WEBUI: magnet:?xt=urn:btih:로 시작안하는 마그넷은 인포해쉬로 간주

v0.0.0.4
- LOGIC: 자체 캐시를 좀 더 적극적으로 활용, 웹에서 검색시 등...

## TODO

- LOGIC: flask_restful 이용해서 api 정리 (sjva에서 설치가 제거된 것 같음)
- LOGIC: --no-cache 옵션
- WEBUI: cosmetic issue, button align, responsive view
- LOGIC: retry 옵션
- LOGIC: proxy 적용
- LOGIC: 메모리 캐시에서 db를 이용하는 것은 잠시 보류
