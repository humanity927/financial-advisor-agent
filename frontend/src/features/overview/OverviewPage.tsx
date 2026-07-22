import { Row, Col } from 'antd';
import SectionHeader from '../../components/SectionHeader';
import HealthCard from './HealthCard';
import SnapshotCard from './SnapshotCard';
import AllocationPreview from './AllocationPreview';
import './OverviewPage.css';

export default function OverviewPage() {
  return (
    <div className="page-layout overview-page">
      <SectionHeader title="总览" subtitle="系统健康、市场快照与配置概览" />
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={10}>
          <HealthCard />
        </Col>
        <Col xs={24} xl={14}>
          <AllocationPreview />
        </Col>
        <Col span={24}>
          <SnapshotCard />
        </Col>
      </Row>
    </div>
  );
}
